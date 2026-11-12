"""Optional Render->Oracle read-only compute router.

Oracle is strictly optional. Every operation defaults to local execution.
This module never submits or retries state-changing game actions.
"""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from collections import Counter
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


class HybridRouter:
    def __init__(self, *, endpoint=None, secret=None, timeout=None,
                 enabled=None, clock=None, transport=None):
        self.endpoint = endpoint if endpoint is not None else os.getenv('HYBRID_ORACLE_URL', '')
        self.secret = secret if secret is not None else os.getenv('HYBRID_SHARED_SECRET', '')
        setting = os.getenv('HYBRID_ENABLED', '0') == '1'
        self.enabled = (setting if enabled is None else bool(enabled))
        self.timeout = float(timeout if timeout is not None else os.getenv('HYBRID_TIMEOUT', '2.5'))
        self.clock = clock or time.monotonic
        self.transport = transport or self._post
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='hybrid-read')
        self.spec_gate = threading.BoundedSemaphore(2)
        self.metrics = Counter()
        self.active = 0
        self.ewma = 0.0
        self.failure_count = 0
        self.open_until = 0.0
        self.mode_setting = os.getenv('HYBRID_MODE', 'auto')
        if self.mode_setting not in ('auto', 'normal', 'speculative', 'offload'):
            self.mode_setting = 'auto'
        parsed = urlsplit(self.endpoint)
        self.ready = (self.enabled and len(self.secret) >= 32
                      and parsed.scheme == 'https' and bool(parsed.hostname)
                      and parsed.username is None and parsed.password is None
                      and not parsed.query and not parsed.fragment
                      and parsed.path in ('', '/', '/internal/compute')
                      and self.timeout > 0 and self.timeout <= 10)
        if self.enabled and not self.ready:
            logging.warning('Hybrid compute disabled: endpoint/secret configuration is invalid')
        if self.endpoint and self.secret and self.ready:
            self.endpoint = self.endpoint.rstrip('/')
            if not self.endpoint.endswith('/internal/compute'):
                self.endpoint += '/internal/compute'

    def started(self):
        with self.lock:
            self.active += 1

    def finished(self, duration):
        with self.lock:
            self.active = max(0, self.active - 1)
            # Track HTTP latency rather than rendering CPU usage as though
            # it were available from the container.
            self.ewma = duration if not self.ewma else (0.15 * duration + 0.85 * self.ewma)

    def mode(self):
        with self.lock:
            if not self.ready or self.clock() < self.open_until:
                return 'normal'
            if self.mode_setting != 'auto':
                return self.mode_setting
            if self.active >= 8 or (self.active >= 4 and self.ewma >= 1.5):
                return 'offload'
            if self.active >= 3 or (self.active >= 2 and self.ewma >= 0.8):
                return 'speculative'
            return 'normal'

    def _post(self, body):
        now = str(int(time.time()))
        signature = hmac.new(self.secret.encode('utf-8'), now.encode('ascii')+b'\n'+body,
                             hashlib.sha256).hexdigest()
        request = Request(self.endpoint, data=body,
                          headers={'Content-Type': 'application/json',
                                   'X-Hybrid-Timestamp': now,
                                   'X-Hybrid-Signature': signature},
                          method='POST')
        with urlopen(request, timeout=self.timeout) as response:
            if response.status != 200:
                raise ValueError('Oracle rejected a compute request')
            length = int(response.headers.get('Content-Length', '0') or 0)
            if length > 2097152:
                raise ValueError('Oracle response was too large')
            raw = response.read(2097153)
            if len(raw) > 2097152:
                raise ValueError('Oracle response exceeded maximum size')
            return json.loads(raw.decode('utf-8'))

    def _remote(self, operation):
        request = json.dumps({'op': operation, 'request_id': os.urandom(12).hex()},
                             separators=(',', ':')).encode('utf-8')
        result = self.transport(request)
        if not isinstance(result, dict) or result.get('operation') != operation:
            raise ValueError('Oracle result is malformed')
        if operation == 'rankings':
            board = result.get('rankings')
            if not isinstance(board, dict) or set(board) != {'manufactured','net_profit','revenue'}:
                raise ValueError('Oracle rankings are incomplete')
            for metric in ('manufactured', 'net_profit', 'revenue'):
                board_item = board[metric]
                if not isinstance(board_item, dict) or not isinstance(board_item.get('individual'), list) or not isinstance(board_item.get('classes'), list):
                    raise ValueError('Oracle rankings are invalid')
            return {'rankings': board}
        raise ValueError('Unsupported compute operation')

    def _success(self):
        with self.lock:
            self.failure_count = 0
            self.open_until = 0

    def _failure(self):
        with self.lock:
            self.failure_count += 1
            self.metrics['oracle_errors'] += 1
            if self.failure_count >= 3:
                self.open_until = self.clock() + 60
                self.metrics['circuit_opened'] += 1

    def calculate(self, operation, local, local_parallel=None):
        if operation != 'rankings':
            return local()
        mode = self.mode()
        with self.lock:
            self.metrics['mode_'+mode] += 1
        if mode == 'normal':
            return local()
        with self.lock:
            self.metrics['forwarded'] += 1
        if mode == 'offload':
            try:
                result = self._remote(operation)
                self._success()
                with self.lock:self.metrics['oracle_won'] += 1
                return result
            except (ValueError, URLError, HTTPError, OSError, TimeoutError) as error:
                self._failure()
                logging.warning('Oracle offload fallback (%s)', type(error).__name__)
                with self.lock:self.metrics['fallback'] += 1
                return local()
        if not self.spec_gate.acquire(blocking=False):
            with self.lock:self.metrics['speculative_limit'] += 1
            return local()
        # Run both READ-ONLY computations using independent DB connections.
        # The loser may complete; this is safe precisely because no writes are
        # permitted in the endpoint.
        try:
            if local_parallel is None:
                return local()
            futures = {self.pool.submit(self._remote, operation): 'oracle',
                       self.pool.submit(local_parallel): 'render'}
            first_success = None
            pending = set(futures)
            end = self.clock() + max(0.5, self.timeout + 3.0)
            while pending and self.clock() < end:
                finished, pending = wait(pending, timeout=max(0, end-self.clock()),
                                         return_when=FIRST_COMPLETED)
                for future in finished:
                    try:
                        value = future.result()
                    except Exception as error:
                        if futures[future] == 'oracle':
                            self._failure()
                            logging.warning('Speculative Oracle request failed (%s)',type(error).__name__)
                        continue
                    first_success = (value, futures[future])
                    break
                if first_success is not None:
                    break
            for future in pending:
                future.cancel()
            if first_success is None:
                with self.lock:self.metrics['fallback'] += 1
                return local()
            value, winner = first_success
            if winner == 'oracle':
                self._success()
            with self.lock:self.metrics[winner+'_won'] += 1
            return value
        finally:
            self.spec_gate.release()

    def stats(self):
        with self.lock:
            return {'enabled':self.ready,'mode':self.mode_setting,'active':self.active,
                    'latency_ewma_ms':round(self.ewma*1000),
                    'circuit_open':self.clock() < self.open_until,
                    'metrics':dict(self.metrics)}

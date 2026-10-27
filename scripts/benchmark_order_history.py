"""Measure a disposable local fixture; never reads production orders."""
import sys,time,json,statistics,tracemalloc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tests.test_order_history import OrderHistory
import order_history,app
fixture=OrderHistory();fixture.setUp()
try:
    fixture.db.execute('BEGIN')
    fixture.seed_orders(10000)
    fixture.db.execute('COMMIT')
    durations=[]
    tracemalloc.start()
    for _ in range(10):
        start=time.perf_counter()
        result=order_history.page(fixture.db,fixture.buyer,{'role':['purchases'],'limit':['20']},vars(app))
        durations.append((time.perf_counter()-start)*1000)
    _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
    print(json.dumps({'scope':'local SQLite synthetic fixture, not production or concurrent-user capacity','seeded_orders':10000,'returned_orders':len(result['items']),'has_more':result['has_more'],'median_ms':round(statistics.median(durations),2),'max_ms':round(max(durations),2),'response_bytes':len(json.dumps(result).encode()),'peak_python_bytes':peak}))
finally:
    fixture.tearDown()

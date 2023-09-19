import time
import random
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from threading import Thread
from threading import Event


def log_request_rate(request_logs, stop_event, time_scale):
    time_cnt = 1
    while not stop_event.is_set():
        current_time = time.time()
        cnt = 0
        for i in range(len(request_logs) - 1, -1, -1):
            if current_time - request_logs[i][1] < 1 / time_scale:
                cnt += 1
            else:
                break
        print(
            f"{time_cnt} Requests done in the last second {int(current_time)}: {cnt} throughout, total requests: {len(request_logs)}, token throughout: {cnt * 3000}, acum {(len(request_logs) * 3000)/1000/1000} million tokens "
        )
        time_cnt += 1
        time.sleep(1 / time_scale)


def perform_request(apikey, request_duration, time_scale):
    sleep_time = random.uniform(
        request_duration[0] / time_scale, request_duration[1] / time_scale
    )
    time.sleep(sleep_time)
    return apikey


def make_request(
    apikey_acumulator, lock, request_duration, request_logs, interval, i, time_scale
):
    print(f"Worker {i} started")
    retry_count = 0
    while True:
        available_apikey = None
        with lock:
            current_time = time.time()
            keys = list(apikey_acumulator.keys())
            start_index = random.randint(0, len(keys) - 1)
            cnt = 0
            while True:
                apikey = keys[start_index]
                data = apikey_acumulator[apikey]
                if len(data["timestamps"]) < data["request_limit"]:
                    # 没满
                    available_apikey = apikey
                    data["timestamps"].append(current_time)
                    break
                elif (
                    len(data["timestamps"]) == data["request_limit"]
                    and current_time - data["timestamps"][0] > interval
                ):
                    # 满了，但是超过interval
                    available_apikey = apikey
                    data["timestamps"].pop(0)
                    data["timestamps"].append(current_time)
                    break
                elif (
                    len(data["timestamps"]) == data["request_limit"]
                    and current_time - data["timestamps"][0] <= interval
                ):
                    # 满了，且没有超过interval
                    start_index = (start_index + 1) % len(keys)
                    cnt += 1
                    if cnt == len(keys):
                        break

        if available_apikey is not None:
            # print(f"Using apikey {available_apikey}")
            start_time = time.time()
            perform_request(available_apikey, request_duration, time_scale)
            end_time = time.time()
            request_logs.append((start_time, end_time, available_apikey))
        else:
            retry_count += 1
            print(f"Try to get valid key failed, retrying...{retry_count}")

        if retry_count >= 5:
            print(
                f"Worker {i} retried {retry_count} times, but get no valid key. Wait for 60 seconds"
            )
            time.sleep(60 / time_scale)
            retry_count = 0


if __name__ == "__main__":
    request_limit = 3  # 每个 key 每个时间间隔最多请求 x 次
    apikey_acumulator = {}  # 每个 key 的请求记录
    request_duration = (8, 15)  # 模拟每个请求的耗时 (x,y)之间
    key_num = 400  # x 个 key
    concurrency = int(key_num / 2)  # x 个并发请求
    interval = 60  # 时间间隔x秒

    time_scale = 100  # 时间缩放比例, 1 表示真实时间, 10 表示时间加快 10 倍
    interval = interval / time_scale

    key_pool = [str(x) for x in range(key_num)]

    for key in key_pool:
        apikey_acumulator[key] = {"timestamps": [], "request_limit": request_limit}

    request_logs = []
    lock = Lock()

    stop_event = Event()
    logger_thread = Thread(
        target=log_request_rate, args=(request_logs, stop_event, time_scale)
    )
    print("Start logger thread")
    logger_thread.start()

    print("Start worker thread")
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for i in range(concurrency):
            executor.submit(
                make_request,
                apikey_acumulator,
                lock,
                request_duration,
                request_logs,
                interval,
                i,
                time_scale,
            )

    stop_event.set()
    logger_thread.join()

import os

def main():
    worker_name = os.getenv("WORKER_NAME")
    if worker_name is None:
        raise ValueError("WORKER_NAME environment variable is not set.")
    try:
        worker_module = __import__(f"hatching.workers.{worker_name}", fromlist=[""])
    except ImportError as e:
        raise ImportError(f"Worker module '{worker_name}' not found.") from e
    worker = getattr(worker_module, "worker", None)
    if worker is None:
        raise AttributeError(f"Worker class not found in module '{worker_name}'.")
    worker.start()

if __name__ == "__main__":
    main()

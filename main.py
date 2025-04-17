import os

import anyio

def main():
    instance_type = os.getenv("INSTANCE_TYPE")
    if instance_type is None:
        raise ValueError("INSTANCE_TYPE environment variable is not set.")
    if instance_type == "worker":
        worker_name = os.getenv("WORKER_NAME")
        if worker_name is None:
            raise ValueError("WORKER_NAME environment variable is not set.")
        try:
            worker_module = __import__(f"temping.workers.{worker_name}", fromlist=[""])
        except ImportError as e:
            raise ImportError(f"Worker module '{worker_name}' not found.") from e
        main = getattr(worker_module, "main", None)
        if main is None:
            raise AttributeError(f"main function not found in module '{worker_name}'.")
        anyio.run(main)
    elif instance_type == "trigger":
        from temping.triggers.http import main
        main()

if __name__ == "__main__":
    main()

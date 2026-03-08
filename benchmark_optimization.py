import time
import uuid
import string
import secrets
from main import KernelManager, generate_nanoid

def benchmark_inversion_impact():
    km = KernelManager()
    nanoid_session = generate_nanoid()
    km.file_id_map[nanoid_session] = {}

    # Pre-populate with many files
    num_existing_files = 1000
    for i in range(num_existing_files):
        fid = generate_nanoid()
        fname = f"file_{i}.txt"
        km.file_id_map[nanoid_session][fid] = fname

    num_new_files = 500
    new_filenames = [f"new_file_{i}.txt" for i in range(num_new_files)]

    # Baseline: Current implementation (inverted dict inside loop)
    start_time = time.perf_counter()
    for fname in new_filenames:
        with km.lock:
            if nanoid_session not in km.file_id_map:
                km.file_id_map[nanoid_session] = {}

            # This is the "expensive" part
            existing_ids = {v: k for k, v in km.file_id_map[nanoid_session].items()}
            if fname in existing_ids:
                file_id = existing_ids[fname]
            else:
                file_id = generate_nanoid()
                km.file_id_map[nanoid_session][file_id] = fname
    end_time = time.perf_counter()
    baseline_duration = end_time - start_time
    print(f"Baseline (inversion inside loop): {baseline_duration:.4f} seconds")

    # Optimized: Inversion outside loop
    km.file_id_map[nanoid_session] = {} # Reset
    for i in range(num_existing_files):
        fid = generate_nanoid()
        fname = f"file_{i}.txt"
        km.file_id_map[nanoid_session][fid] = fname

    start_time = time.perf_counter()
    with km.lock:
        if nanoid_session not in km.file_id_map:
            km.file_id_map[nanoid_session] = {}
        existing_ids = {v: k for k, v in km.file_id_map[nanoid_session].items()}

    for fname in new_filenames:
        with km.lock:
            if fname in existing_ids:
                file_id = existing_ids[fname]
            else:
                file_id = generate_nanoid()
                km.file_id_map[nanoid_session][file_id] = fname
                existing_ids[fname] = file_id # Keep in sync
    end_time = time.perf_counter()
    optimized_duration = end_time - start_time
    print(f"Optimized (inversion outside loop): {optimized_duration:.4f} seconds")

    improvement = (baseline_duration - optimized_duration) / baseline_duration * 100
    print(f"Improvement: {improvement:.2f}%")

if __name__ == "__main__":
    benchmark_inversion_impact()

import json
import csv
import os
import glob
import multiprocessing
import random
import time
from core.crypto import UmaCrypto
from core.provider import UmaProvider
from core.processor import UmaProcessor

# --- CONFIGURATION ---
# Removed 'Transcript', Added 'AudioLength' and 'CharacterPerSecond'
STORY_CSV_COLUMNS = [
    'StoryId', 'BlockIndex', 'CharaId', 'SpeakerName', 'Text', 'RubyText', 
    'VoiceSheetId', 'CueId', 'AudioFilePath', 'AudioLength', 'CharacterPerSecond'
]
SYSTEM_CSV_COLUMNS = ['Text', 'CharaId', 'AudioFilePath']

# --- HELPER FUNCTIONS ---
def parse_blocks(env):
    """
    Parses timeline blocks using NextBlock logic to determine the correct ID.
    Returns a Dictionary: { BlockIndex: Data }
    """
    raw_objects = []
    
    # 1. Read all Potential Text Objects
    for obj in env.objects:
        if obj.type.name == "MonoBehaviour":
            try:
                data = obj.read()
                if hasattr(data, 'Text'):
                    raw_objects.append(data)
            except: 
                continue
    
    if not raw_objects: return {}

    # 2. Calculate Block Indices (NextBlock - 1 Logic)
    next_blocks = [getattr(t, 'NextBlock', -1) for t in raw_objects]
    valid_nexts = [n for n in next_blocks if n != -1]
    
    last_block_num = max(valid_nexts) if valid_nexts else 0
    blocks_map = {}
    
    for data in raw_objects:
        next_blk = getattr(data, 'NextBlock', -1)
        if next_blk == -1:
            block_idx = last_block_num
        else:
            block_idx = next_blk - 1
            
        blocks_map[block_idx] = {
            'SpeakerName': getattr(data, 'Name', ''),
            'Text': getattr(data, 'Text', ''),
            'CharaId': getattr(data, 'CharaId', 0),
            'VoiceSheetId': getattr(data, 'VoiceSheetId', ''),
            'CueId': getattr(data, 'CueId', -1),
            'RubyInfo': '', 
            'BlockIndex': block_idx 
        }
    return blocks_map

def apply_ruby(env_ruby, blocks_map):
    """
    Applies Ruby to the blocks_map using the Dictionary Key (BlockIndex).
    """
    if not env_ruby: return

    for obj in env_ruby.objects:
        if obj.type.name == "MonoBehaviour":
            try:
                data = obj.read()
                ruby_data = getattr(data, 'DataArray', getattr(data, 'm_DataArray', None))
                
                if ruby_data:
                    for rb in ruby_data:
                        target_idx = rb.BlockIndex
                        if target_idx in blocks_map:
                            r_list = []
                            r_items = getattr(rb, 'RubyDataList', getattr(rb, 'm_RubyDataList', []))
                            
                            for r in r_items:
                                # Use CharX (float) matching reference script
                                char_pos = getattr(r, 'CharX', getattr(r, 'CharIndex', 0))
                                text = getattr(r, 'RubyText', '')
                                r_list.append(f"{char_pos}:{text}")
                            
                            if r_list:
                                blocks_map[target_idx]['RubyInfo'] = " | ".join(r_list)
                    return 
            except: continue

# --- WORKER: SYSTEM SCAN ---
def system_worker_task(worker_id, chunk, config):
    try:
        processor = UmaProcessor(config)
        temp_filename = f"temp_sys_worker_{worker_id}.csv"
        
        with open(temp_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=SYSTEM_CSV_COLUMNS)
            for entry in chunk:
                c_id = entry['character_id']
                out_dir = os.path.join(processor.cfg['PATHS']['output'], "system", str(c_id))
                fname = f"sys_{c_id}_{entry['cue_sheet']}_{entry['cue_id']}.wav"
                wav_path = os.path.join(out_dir, fname)
                
                # Unpack tuple (path, duration), ignore duration for system scan
                final_path, _ = processor.extract_only(
                    entry['acb_path'], entry['awb_path'], entry['cue_id'], wav_path
                )
                if final_path:
                    writer.writerow({
                        'Text': entry['transcript'], 'CharaId': entry['character_id'], 'AudioFilePath': final_path
                    })
        return f"SysWorker {worker_id} done."
    except Exception as e:
        return f"SysWorker {worker_id} CRASHED: {e}"

def run_system_scan(config, test_mode=False):
    print("\n=== PHASE 1: SYSTEM TEXT SCAN ===")
    
    crypto = UmaCrypto(config)
    provider = UmaProvider(crypto, config)
    system_map = provider.get_global_system_voice_map()
    random.shuffle(system_map)
    
    if test_mode: system_map = system_map[:1000]
        
    num_workers = max(1, (os.cpu_count() or 4))
    print(f"  -> Processing {len(system_map)} entries with {num_workers} processes...")
    
    chunk_size = len(system_map) // num_workers + 1
    chunks = [system_map[i:i + chunk_size] for i in range(0, len(system_map), chunk_size)]
    
    pool_args = []
    for i, chunk in enumerate(chunks):
        pool_args.append((i, chunk, config))
        
    with multiprocessing.Pool(processes=num_workers) as pool:
        pool.starmap(system_worker_task, pool_args)

    print("Merging System CSVs...")
    final_csv = 'global_system_voices.csv'
    with open(final_csv, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=SYSTEM_CSV_COLUMNS)
        writer.writeheader()
        count = 0
        for temp_file in glob.glob("temp_sys_worker_*.csv"):
            if os.path.exists(temp_file):
                with open(temp_file, 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read())
                os.remove(temp_file)
                count += 1
    print(f"System Scan Complete. Merged {count} files.")

# --- WORKER: STORY SCAN ---
def story_worker_task(worker_id, story_chunk, shared_audio_map, config):
    try:
        crypto = UmaCrypto(config)
        processor = UmaProcessor(config)
        temp_filename = f"temp_story_worker_{worker_id}.csv"
        
        with open(temp_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=STORY_CSV_COLUMNS)
            
            for packet in story_chunk:
                story_id = packet['story_id']
                try:
                    env_tl = crypto.decrypt_asset(packet['timeline'])
                    blocks_map = parse_blocks(env_tl)
                    if not blocks_map: continue
                    
                    if packet['ruby']:
                        try:
                            env_ruby = crypto.decrypt_asset(packet['ruby'])
                            apply_ruby(env_ruby, blocks_map)
                        except: pass

                    sorted_indices = sorted(blocks_map.keys())
                    for idx in sorted_indices:
                        block = blocks_map[idx]
                        if not block['Text'] and block['CueId'] == -1: continue

                        vs_id = str(block['VoiceSheetId'])
                        cue_id = block['CueId']
                        audio_path = ""
                        audio_len = -1.0
                        cps = -1.0
                        
                        info = shared_audio_map.get(vs_id)
                        if info and cue_id != -1 and info['acb_path']:
                            out_dir = os.path.join(processor.cfg['PATHS']['output'], "story", story_id)
                            fname = f"{vs_id}_{cue_id:03d}.wav"
                            target_path = os.path.join(out_dir, fname)
                            
                            extracted_path, duration = processor.extract_only(
                                info['acb_path'], info['awb_path'], cue_id, target_path
                            )
                            
                            if extracted_path: 
                                audio_path = extracted_path
                                audio_len = round(duration, 4)
                            else: 
                                audio_path = "FAILED"
                        
                        # Calculate CPS (Characters Per Second)
                        if audio_len > 0 and block['Text']:
                            cps = round(len(block['Text']) / audio_len, 2)

                        writer.writerow({
                            'StoryId': story_id, 
                            'BlockIndex': block['BlockIndex'], 
                            'CharaId': block['CharaId'],
                            'SpeakerName': block['SpeakerName'], 
                            'Text': block['Text'],
                            'RubyText': block['RubyInfo'], 
                            'VoiceSheetId': block['VoiceSheetId'],
                            'CueId': block['CueId'], 
                            'AudioFilePath': audio_path, 
                            'AudioLength': audio_len,
                            'CharacterPerSecond': cps
                        })
                except Exception as e:
                    print(f"[{worker_id}] Error {story_id}: {e}")
        return f"StoryWorker {worker_id} done."
    except Exception as e:
        return f"StoryWorker {worker_id} CRASHED: {e}"

def run_story_scan(config, test_mode=False):
    print("\n=== PHASE 2: STORY SCAN ===")
    
    manager = multiprocessing.Manager()
    shared_audio_map = manager.dict()
    
    crypto = UmaCrypto(config)
    provider = UmaProvider(crypto, config)
    
    print("Building global audio index...")
    meta_con = crypto.get_meta_connection()
    raw_audio_map = provider._get_global_audio_index(meta_con.cursor())
    shared_audio_map.update(raw_audio_map)
    
    print("Collecting story packets...")
    all_packets = []
    
    query = "SELECT n, h, e FROM a WHERE n LIKE '%storytimeline_%' AND n NOT LIKE '%resource%'"
    timeline_rows = meta_con.cursor().execute(query).fetchall()
    ruby_index = provider._get_global_ruby_index(meta_con.cursor())
    
    for t_name, t_hash, t_key in timeline_rows:
        story_id_str = t_name.split('_')[-1]
        t_item = {
            'name': t_name, 'hash': t_hash, 'encryption_key': t_key,
            'path': os.path.join(config['PATHS']['dat'], t_hash[:2], t_hash)
        }
        all_packets.append({
            'story_id': story_id_str, 'timeline': t_item,
            'ruby': ruby_index.get(story_id_str)
        })

    random.shuffle(all_packets)
    if test_mode: all_packets = all_packets[:1000]

    num_workers = max(1, (os.cpu_count() or 4))
    print(f"Spawning {num_workers} workers for {len(all_packets)} stories...")
    
    chunk_size = len(all_packets) // num_workers + 1
    chunks = [all_packets[i:i + chunk_size] for i in range(0, len(all_packets), chunk_size)]
    
    pool_args = []
    for i, chunk in enumerate(chunks):
        pool_args.append((i, chunk, shared_audio_map, config))

    with multiprocessing.Pool(processes=num_workers) as pool:
        results_iterator = pool.starmap_async(story_worker_task, pool_args)
        for result in results_iterator.get():
            print(f"  -> {result}")

    print("Merging Story CSVs...")
    final_csv = 'global_story_deep_scan.csv'
    with open(final_csv, 'w', newline='', encoding='utf-8') as outfile:
        writer = csv.DictWriter(outfile, fieldnames=STORY_CSV_COLUMNS)
        writer.writeheader()
        count = 0
        for temp_file in glob.glob("temp_story_worker_*.csv"):
            if os.path.exists(temp_file):
                with open(temp_file, 'r', encoding='utf-8') as infile:
                    outfile.write(infile.read())
                os.remove(temp_file)
                count += 1
    print(f"Story Scan Complete. Merged {count} files.")

# --- WORKER: OVERCLOCKING STRESS ---
def stress_worker_task(worker_id, chunk, config):
    """
    CPU/RAM Stress with Integrity Check.
    Calculates a checksum of all decrypted text and coordinates.
    Returns: { 'story_id': checksum_int }
    """
    crypto = UmaCrypto(config)
    checksums = {}
    
    for packet in chunk:
        story_id = packet['story_id']
        local_sum = 0
        try:
            # 1. Decrypt Timeline (Heavy Integer Math)
            env_tl = crypto.decrypt_asset(packet['timeline'])
            blocks_map = parse_blocks(env_tl)
            
            # 2. Decrypt Ruby
            if packet['ruby']:
                env_ruby = crypto.decrypt_asset(packet['ruby'])
                apply_ruby(env_ruby, blocks_map)
            
            # 3. Calculate Checksum (Verify Integrity)
            for idx, block in blocks_map.items():
                local_sum += idx
                if block['Text']:
                    for char in block['Text']: local_sum += ord(char)
                if block['SpeakerName']:
                    for char in block['SpeakerName']: local_sum += ord(char)
                if block['RubyInfo']:
                    for char in block['RubyInfo']: local_sum += ord(char)

            checksums[story_id] = local_sum
        except Exception:
            checksums[story_id] = -1 
    return checksums

def run_stress_test(config):
    print("\n=== PHASE 3: OVERCLOCKING STRESS TEST (Integrity Mode) ===")
    print("  [Info] Running Decryption -> Parsing -> Checksum.")
    print("  [Info] Any calculation error will trigger a WHEA-style alert.")
    print("  [Info] Press Ctrl+C to stop.\n")
    
    crypto = UmaCrypto(config)
    provider = UmaProvider(crypto, config)
    
    print("Loading asset map...")
    meta_con = crypto.get_meta_connection()
    
    query = "SELECT n, h, e FROM a WHERE n LIKE '%storytimeline_%' AND n NOT LIKE '%resource%'"
    timeline_rows = meta_con.cursor().execute(query).fetchall()
    ruby_index = provider._get_global_ruby_index(meta_con.cursor())
    
    all_packets = []
    for t_name, t_hash, t_key in timeline_rows:
        story_id_str = t_name.split('_')[-1]
        t_item = {
            'name': t_name, 'hash': t_hash, 'encryption_key': t_key,
            'path': os.path.join(config['PATHS']['dat'], t_hash[:2], t_hash)
        }
        all_packets.append({
            'story_id': story_id_str, 'timeline': t_item,
            'ruby': ruby_index.get(story_id_str)
        })

    num_workers = max(1, (os.cpu_count() or 4))
    print(f"Spawning {num_workers} workers for {len(all_packets)} items...")
    
    # BASELINE PASS (Loop 0)
    print("  -> Generating Baseline Checksums (Loop 0)...")
    baseline_checksums = {}
    
    chunk_size = len(all_packets) // num_workers + 1
    chunks = [all_packets[i:i + chunk_size] for i in range(0, len(all_packets), chunk_size)]
    pool_args = []
    for i, chunk in enumerate(chunks):
        pool_args.append((i, chunk, config))
        
    with multiprocessing.Pool(processes=num_workers) as pool:
        results = pool.starmap(stress_worker_task, pool_args)
        
    for res in results:
        baseline_checksums.update(res)
        
    print(f"  -> Baseline created for {len(baseline_checksums)} files.")
    
    # STRESS LOOP
    loop_count = 1
    try:
        while True:
            print(f"  -> Starting Loop {loop_count}...")
            start_time = time.time()
            random.shuffle(all_packets)
            chunks = [all_packets[i:i + chunk_size] for i in range(0, len(all_packets), chunk_size)]
            pool_args = [(i, chunk, config) for i, chunk in enumerate(chunks)]
            
            with multiprocessing.Pool(processes=num_workers) as pool:
                loop_results = pool.starmap(stress_worker_task, pool_args)
            
            errors = 0
            for res_dict in loop_results:
                for s_id, current_sum in res_dict.items():
                    base_sum = baseline_checksums.get(s_id, 0)
                    if current_sum != base_sum:
                        print(f"\n[FATAL ERROR] Checksum Mismatch on Story {s_id}!")
                        print(f"  Expected: {base_sum}, Got: {current_sum}")
                        errors += 1
            
            duration = time.time() - start_time
            if errors > 0:
                print(f"  -> Loop {loop_count} FAILED with {errors} errors in {duration:.2f}s")
            else:
                print(f"  -> Loop {loop_count} PASSED in {duration:.2f}s")
                
            loop_count += 1
            
    except KeyboardInterrupt:
        print("\n\n*** Stress Test Stopped by User ***\n")

# --- MAIN ENTRY POINT ---
def main():
    multiprocessing.freeze_support()
    if not os.path.exists('config/keys.json'):
        print("Error: config/keys.json not found.")
        return

    with open('config/keys.json', 'r') as f: 
        config = json.load(f)

    if not os.path.exists(config['PATHS']['output']):
        os.makedirs(config['PATHS']['output'])

    while True:
        print("\n=== UMA VOICE DATASET CREATOR & STRESS TESTER ===")
        qn_num = 1
        do_stress = False
        if config['EXPOSE_STRESS_MODE']:
            do_stress_str = input(f"{qn_num}. Do story scan stress test? (Y/N): ").strip().upper()
            qn_num += 1
            do_stress = (do_stress_str == 'Y')
        do_system_str = "F"
        do_story_str = "F"
        if not do_stress:
            do_system_str = input(f"{qn_num}. Do system text scan? (Y/N): ").strip().upper()
            qn_num += 1
            do_story_str = input(f"{qn_num}. Do full story scan? (Y/N): ").strip().upper()
            qn_num += 1
        
        
        do_system = (do_system_str == 'Y')
        do_story = (do_story_str == 'Y')
        if not do_system and not do_story:
            if config['EXPOSE_STRESS_MODE'] and not do_stress or not config['EXPOSE_STRESS_MODE']:
                print("\nAt least system or story has to be selected. Restarting selection...\n")
                continue
        
        do_test = False
        if not do_stress and (do_system or do_story):
            do_test_str = input(f"{qn_num}. Enable Test Mode (Limit 1000 rows)? (Y/N): ").strip().upper()
            qn_num += 1
            do_test = (do_test_str == 'Y')
        
        print("\n--- CONFIRM OPTIONS ---")
        if config['EXPOSE_STRESS_MODE']:
            print(f"  > Stress Test:   {'[YES] (Infinite Loop)' if do_stress else '[NO]'}")
        if not do_stress:
            print(f"  > System Scan:   {'[YES]' if do_system else '[NO]'}")
            print(f"  > Story Scan:    {'[YES]' if do_story else '[NO]'}")
            print(f"  > Test Mode:     {'[YES] (Limit 1000)' if do_test else '[NO] (Full Scan)'}")
        print("-----------------------")
        
        confirm = input("Confirm selection? (Y/N): ").strip().upper()
        
        if confirm == 'Y':
            break
        else:
            print("\nRestarting selection...\n")

    print("\nStarting Engine...")
    
    if do_stress:
        run_stress_test(config)
    else:
        if do_system:
            run_system_scan(config, test_mode=do_test)
        if do_story:
            run_story_scan(config, test_mode=do_test)

    print("\nALL OPERATIONS COMPLETE.")

if __name__ == "__main__":
    main()
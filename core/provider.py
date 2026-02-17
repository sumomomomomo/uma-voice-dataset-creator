import sqlite3
import os

class UmaProvider:
    def __init__(self, crypto_module, config):
        self.crypto = crypto_module
        self.cfg = config

    # =========================================================================
    # PART A: SYSTEM VOICES (Database Scan)
    # =========================================================================
    def get_global_system_voice_map(self):
        master_con = sqlite3.connect(self.cfg['PATHS']['master'])
        master_cur = master_con.cursor()
        
        print("Scanning master.mdb for system voices...")
        query = """
        SELECT character_id, text, cue_sheet, cue_id 
        FROM character_system_text 
        WHERE cue_sheet IS NOT NULL AND cue_sheet != ''
        """
        system_entries = master_cur.execute(query).fetchall()
        print(f"Found {len(system_entries)} system voice entries.")

        unique_sheets = set(row[2] for row in system_entries)
        sheet_to_hash_map = self._batch_resolve_sheets(unique_sheets)

        results = []
        for char_id, text, sheet_name, cue_id in system_entries:
            if sheet_name not in sheet_to_hash_map: continue
            file_info = sheet_to_hash_map[sheet_name]
            results.append({
                'character_id': char_id, 'transcript': text,
                'cue_sheet': sheet_name, 'cue_id': cue_id,
                'acb_path': file_info['acb_path'], 'awb_path': file_info['awb_path']
            })
        return results

    def _batch_resolve_sheets(self, sheet_names):
        """Global Indexing: Scans meta ONCE to build a fast lookup table."""
        meta_con = self.crypto.get_meta_connection()
        meta_cur = meta_con.cursor()
        resolved_map = {}
        
        print(f"Building global sound index for {len(sheet_names)} sheets...")
        query = "SELECT n, h, e FROM a WHERE n LIKE 'sound/%'"
        all_sounds = meta_cur.execute(query).fetchall()
        
        temp_index = {}
        for n, h, e in all_sounds:
            basename = n.split('/')[-1].split('.')[0]
            if basename not in temp_index:
                temp_index[basename] = {'acb_path': None, 'awb_path': None}
            
            full_path = os.path.join(self.cfg['PATHS']['dat'], h[:2], h)
            if ".acb" in n: temp_index[basename]['acb_path'] = full_path
            elif ".awb" in n: temp_index[basename]['awb_path'] = full_path

        for sheet in sheet_names:
            if sheet in temp_index and temp_index[sheet]['acb_path']:
                resolved_map[sheet] = temp_index[sheet]
                
        print(f"Index built. Found {len(resolved_map)} matching sheets.")
        return resolved_map

    # =========================================================================
    # PART B: STORY MODE (Global Index - Zero Decryption)
    # =========================================================================
    
    def _get_global_ruby_index(self, meta_cur):
        """Builds a map of all ruby assets in one pass."""
        print("  -> Indexing all Ruby assets...")
        query = "SELECT n, h, e FROM a WHERE n LIKE '%ast_ruby_%'"
        rows = meta_cur.execute(query).fetchall()
        
        ruby_index = {}
        for n, h, e in rows:
            # Format: .../ast_ruby_100123
            story_id = n.split('_')[-1]
            ruby_index[story_id] = {
                'name': n, 'hash': h, 'encryption_key': e,
                'path': os.path.join(self.cfg['PATHS']['dat'], h[:2], h)
            }
        return ruby_index

    def _get_global_audio_index(self, meta_cur):
        """
        Builds a map of ALL 'snd_voi_story' files in the game.
        This allows main.py to look up ANY VoiceSheetId instantly without
        us needing to decrypt the timeline here to find out which one it is.
        """
        print("  -> Indexing all Story Audio (snd_voi_story)...")
        query = "SELECT n, h, e FROM a WHERE n LIKE '%snd_voi_story_%'"
        rows = meta_cur.execute(query).fetchall()
        
        audio_index = {}
        for n, h, e in rows:
            # Format: .../snd_voi_story_100123.acb
            basename = n.split('/')[-1]
            name_no_ext = basename.split('.')[0]
            
            # Extract VoiceSheetId (last segment after underscore)
            parts = name_no_ext.split('_')
            if not parts: continue
            vs_id = parts[-1] 
            
            if vs_id not in audio_index:
                audio_index[vs_id] = {'acb_path': None, 'awb_path': None}
            
            full_path = os.path.join(self.cfg['PATHS']['dat'], h[:2], h)
            if ".acb" in n: audio_index[vs_id]['acb_path'] = full_path
            elif ".awb" in n: audio_index[vs_id]['awb_path'] = full_path
            
        return audio_index

    def get_all_story_parts(self):
        meta_con = self.crypto.get_meta_connection()
        meta_cur = meta_con.cursor()

        # 1. Pre-calculate EVERYTHING (Approx 1-2 seconds)
        ruby_index = self._get_global_ruby_index(meta_cur)
        global_audio_map = self._get_global_audio_index(meta_cur)

        print("Scanning meta for all Story Timelines...")
        query = "SELECT n, h, e FROM a WHERE n LIKE '%storytimeline_%' AND n NOT LIKE '%resource%'"
        timeline_rows = meta_cur.execute(query).fetchall()
        
        total = len(timeline_rows)
        print(f"Found {total} storylines. Generator ready.")

        # 2. Fast Yield
        # We pass the same 'global_audio_map' reference to every packet.
        # This is memory efficient (reference only) and allows main.py to 
        # resolve ANY pointer it finds inside the timeline.
        for idx, (t_name, t_hash, t_key) in enumerate(timeline_rows):
            story_id_str = t_name.split('_')[-1]
            
            timeline_item = {
                'name': t_name, 'hash': t_hash, 'encryption_key': t_key,
                'path': os.path.join(self.cfg['PATHS']['dat'], t_hash[:2], t_hash)
            }
            
            # O(1) Lookup
            ruby_item = ruby_index.get(story_id_str)

            yield {
                'story_id': story_id_str, 
                'timeline': timeline_item,
                'ruby': ruby_item, 
                'audio_map': global_audio_map  # Pass the global index!
            }
            
            if idx % 1000 == 0: 
                print(f"  -> Queued {idx}/{total}...")
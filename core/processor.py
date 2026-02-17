import os
import acb
import sys

sys.path.append("..")
import libpyvgmstream

class UmaProcessor:
    def __init__(self, config):
        self.cfg = config
        self.pipe = None 

    def extract_only(self, acb_path, awb_path, cue_id, output_path):
        """Thread-safe extraction to WAV. Returns path if successful."""
        if os.path.exists(output_path): return output_path

        try:
            acb_file = acb.ACBFile(acb_path, awb_path, hca_keys=self.cfg['UMA_HCA_KEY'])
            track = None
            
            # 1. System Voice (Attribute Lookup)
            for t in acb_file.track_list.tracks:
                if getattr(t, 'cue_id', None) == cue_id:
                    track = t
                    break
            
            # 2. Story Voice (Index Fallback)
            if not track and isinstance(cue_id, int) and cue_id < len(acb_file.track_list.tracks):
                track = acb_file.track_list.tracks[cue_id]

            if not track: return None

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            wav_bytes = libpyvgmstream.convert(acb_file.get_track_data(track, True), "hca")
            with open(output_path, "wb") as out_file:
                out_file.write(wav_bytes)

            return output_path if os.path.exists(output_path) else None

        except Exception as e:
            print(e)
            return None
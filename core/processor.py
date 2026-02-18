import os
import acb
import sys
import wave
import io

sys.path.append("..")
import libpyvgmstream

class UmaProcessor:
    def __init__(self, config):
        self.cfg = config
        self.pipe = None 

    def extract_only(self, acb_path, awb_path, cue_id, output_path):
        """
        Thread-safe extraction to WAV. 
        Returns (path, duration_seconds) if successful, else (None, 0).
        """
        # If file exists, try to read duration from it
        if os.path.exists(output_path): 
            try:
                with wave.open(output_path, 'rb') as f:
                    frames = f.getnframes()
                    rate = f.getframerate()
                    duration = frames / float(rate)
                    return output_path, duration
            except:
                return output_path, 0

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

            if not track: return None, 0

            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            wav_bytes = libpyvgmstream.convert(acb_file.get_track_data(track, True), "hca")
            
            # Calculate duration from bytes in memory
            duration = 0
            try:
                with io.BytesIO(wav_bytes) as wav_io:
                    with wave.open(wav_io, 'rb') as wav_ref:
                        frames = wav_ref.getnframes()
                        rate = wav_ref.getframerate()
                        duration = frames / float(rate)
            except Exception as e:
                print(f"Duration calc error: {e}")

            with open(output_path, "wb") as out_file:
                out_file.write(wav_bytes)

            return (output_path, duration) if os.path.exists(output_path) else (None, 0)

        except Exception as e:
            print(e)
            return None, 0
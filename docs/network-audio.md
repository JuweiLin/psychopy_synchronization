# GPU audio service

After Condition 1 saves personal WPM, the display computer sends one request per selected Condition 2 sentence to the GPU service. The service generates and validates a complete WAV before publishing it. The display computer polls and downloads in a background thread, then verifies identity, checksum, file size, PCM readability and duration before caching the sentence.

The experiment's local files are `assets/TTS/<participant_id>/<session_id>/<article_id>/sentence_0001.wav`, with one JSON metadata file per WAV and a `tts_index.csv` mapping every sentence to its audio location. With `tts_server_url=""` in the root `config.py`, only requests and the index/manifest are saved. Condition 2 playback is not implemented.

## Start the GPU service

Both computers need the project code. Only the GPU computer needs F5-TTS and its model dependencies. Prepare the environment using the [official F5-TTS repository](https://github.com/SWivid/F5-TTS), plus a fixed reference WAV and its transcript.

```sh
python -m gpu_service.tts_server \
  --host 0.0.0.0 \
  --port 8765 \
  --output-dir generated_audio \
  --ref-audio /path/to/reference.wav \
  --ref-text-file /path/to/reference.txt \
  --device cuda \
  --wpm-tolerance 0.05
```

Replace the reference paths. Set `tts_server_url` in the display computer's root `config.py` to the GPU computer's actual origin, for example `"http://192.168.1.20:8765"`, and reopen the launcher. The server defaults to loopback unless `--host` is set. This HTTP service is intended for the experiment LAN and has no account authentication.

Run from the project root in the GPU computer's F5-TTS Python environment. The equivalent single-line command works in Windows PowerShell/CMD and Linux/macOS shells (replace both reference paths):

```sh
python -m gpu_service.tts_server --host 0.0.0.0 --port 8765 --output-dir generated_audio --ref-audio "reference.wav" --ref-text-file "reference.txt" --device cuda
```

`reference.wav` is the reference voice audio; `reference.txt` is its exact transcript. Keep the server running during the experiment. From the display computer, open `http://<GPU_IP>:8765/health` to check reachability; a health response does not confirm that model inference works. The two computers must be able to reach each other on port 8765.

The model loads on the first request, then a single worker reuses it. The adapter maps target duration to F5-TTS inference duration, including reference duration in `fix_duration`. It does not pass WPM directly as relative model speed. Long tasks can be split internally and joined, but still produce one WAV for the requested sentence. See the [official inference implementation](https://github.com/SWivid/F5-TTS/blob/main/src/f5_tts/infer/utils_infer.py).

The 5% WPM tolerance is a configurable engineering default, not a finalized experiment criterion. Duration includes generated pauses and leading/trailing silence. Content accuracy and voice quality require listening checks; automatic ASR content verification is not implemented. Real F5-TTS has not been tested on this setup.

## Request contract

The outer JSON key remains `articles` for compatibility; each item is one audio task. The experiment creates this automatically from its selected CSV pages.

```json
{
  "articles": [
    {
      "session_id": "run01",
      "participant_id": "S001",
      "article_id": "article_001",
      "sentence_index": 1,
      "text": "The first sentence goes here.",
      "word_count": 5,
      "target_wpm": 240.0
    }
  ]
}
```

The target duration above is 1.25 seconds. Word count must equal `len(text.split())`. Sentence index is a positive integer and forms part of identity with participant, session and article IDs. Duplicate identities in one batch are rejected. The API accepts 1–100 tasks per batch and at most 1 MiB of JSON; the background client splits longer lists into batches of 100.

Standalone tasks without `sentence_index` remain supported for compatibility. The experiment always uses sentence-based generation.

## API and files

| Endpoint | Result |
| --- | --- |
| `GET /health` | Service response; does not validate GPU/model readiness |
| `POST /jobs/batch` | Validates the batch, queues tasks and returns job IDs |
| `GET /jobs/<job_id>` | Current state and metadata |
| `GET /jobs/<job_id>/audio` | Complete WAV; unfinished audio returns HTTP 409 |

```text
generated_audio/<job_id>/
  audio.partial.wav   # unavailable while generating
  audio.wav           # published after validation
  metadata.json
```

Metadata records identity, text hash, target speed/duration, actual duration/WPM, sample rate, checksum, file size, model information and errors. Cache completion is delivered as `CachedAudio`; failures as `AudioFailure`. Cached audio has not yet been preloaded or played by PsychoPy.

Failed tasks are recorded while later tasks continue. Service restarts preserve completed jobs; unfinished jobs become failed and require resubmission. Automatic network retry is not implemented. Escape stops local polling/downloads and retains cached audio, but does not cancel accepted GPU jobs.

## Independent transport test

For HTTP/file testing without a model:

```sh
python -m gpu_service.tts_server --demo --host 127.0.0.1 --port 8765
```

In another terminal, use a `requests.json` saved by a completed Condition 1 session. Replace the placeholder path below:

```sh
python -m psychopy_sync.audio_client \
  --server http://127.0.0.1:8765 \
  --articles /path/to/session/requests.json \
  --cache-dir audio_cache
```

Demo mode produces explicitly marked silence, which the formal sound preload helper rejects. It is not experimental speech. Integration tests use temporary local HTTP services for sentence identity, indexing, batching, publication, checksum validation, failure handling and restart recovery.

"""tests/test_file_voice.py — 文件上传（②）+ 语音（③④⑤）。"""
import sys, os, io, zipfile, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from backend.file_service import FileService
from backend.voice_service import VoiceService, ASRService, TTSService


# ---------- 文件上传 ----------
def test_text_file_parsed():
    s = FileService()
    r = s.ingest("notes.txt", "你好世界".encode("utf-8"), session_id="s1")
    assert r["kind"] == "text" and r["has_text"]
    assert "你好世界" in s.get(r["id"]).parsed_text


def test_size_limit():
    s = FileService()
    try:
        s.ingest("big.txt", b"x" * (21 * 1024 * 1024)); assert False
    except ValueError:
        pass


def test_filename_sanitized():
    s = FileService()
    r = s.ingest("../../etc/passwd", b"data")
    assert "/" not in r["filename"] and ".." not in r["filename"]


def test_zip_lists_manifest_not_extracted():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "aaa"); z.writestr("b/c.py", "print(1)")
    s = FileService()
    r = s.ingest("pkg.zip", buf.getvalue())
    assert r["kind"] == "archive"
    txt = s.get(r["id"]).parsed_text
    assert "a.txt" in txt and "c.py" in txt and "压缩包含" in txt


def test_pdf_image_only_stored_with_note():
    s = FileService()
    pdf = s.ingest("doc.pdf", b"%PDF-1.4 fake")
    img = s.ingest("pic.png", b"\x89PNG fake")
    assert pdf["kind"] == "document" and not pdf["has_text"] and pdf["note"]
    assert img["kind"] == "image" and img["note"]


def test_context_text_combines():
    s = FileService()
    a = s.ingest("a.txt", "alpha".encode(), session_id="s1")
    b = s.ingest("b.png", b"img", session_id="s1")
    ctx = s.context_text([a["id"], b["id"]])
    assert "alpha" in ctx and "b.png" in ctx


def test_list_for_session():
    s = FileService()
    s.ingest("a.txt", b"x", session_id="s1")
    s.ingest("b.txt", b"y", session_id="s2")
    assert len(s.list_for_session("s1")) == 1


# ---------- 语音：诚实降级（未接真模型不假装成功）----------
def test_asr_mock_does_not_fake_transcription():
    r = ASRService(backend="mock").transcribe(b"audiobytes")
    assert r["text"] == "" and "未" in r["note"]  # 不假装识别出内容


def test_tts_mock_does_not_fake_audio():
    r = TTSService(backend="mock").synthesize("你好")
    assert r["available"] is False and not r["audio_b64"]


def test_tts_empty_text_rejected():
    assert TTSService(backend="mock").synthesize("  ")["available"] is False


def test_tts_voices_per_backend():
    assert any("晓晓" in v["name"] for v in TTSService(backend="edge").list_voices())
    assert any("MOSS" in v["name"] for v in TTSService(backend="moss").list_voices())


def test_voice_config_reports_availability():
    cfg = VoiceService().config()
    assert cfg["asr"]["available"] is False  # 默认 mock 未接
    assert "voices" in cfg["tts"]

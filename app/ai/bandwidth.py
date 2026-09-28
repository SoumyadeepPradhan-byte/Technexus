"""
app/ai/bandwidth.py  –  LOW-BANDWIDTH ROBUSTNESS: pick the consultation mode the network can carry.

The app measures its connection (a 50 KB download takes X ms → kbps) and sends the numbers here.
v0 = thresholds. Upgrade path: learn from dropped-call history per village / time of day.
"""


def recommend_mode(kbps: float | None, latency_ms: float | None = None, packet_loss_pct: float | None = None,
                   low_bandwidth_kbps: int = 300) -> dict:
    """returns {mode: video|audio|text, video_quality, reason, max_bitrate_kbps}"""
    if kbps is None:
        return {"mode": "audio", "video_quality": None, "reason": "network not measured; audio is the safe default",
                "max_bitrate_kbps": 64}
    if kbps >= 800:
        mode, q, reason, br = "video", "360p", f"{kbps:.0f} kbps supports low-res video", 500
    elif kbps >= low_bandwidth_kbps:
        mode, q, reason, br = "video", "180p", f"{kbps:.0f} kbps: very low-res video", 200
    elif kbps >= 60:
        mode, q, reason, br = "audio", None, f"{kbps:.0f} kbps is too slow for video; audio call", 32
    else:
        mode, q, reason, br = "text", None, f"{kbps:.0f} kbps: text + photos, doctor replies when online", 0

    # Bad latency / loss downgrades one step (video → audio → text)
    if (latency_ms and latency_ms > 600) or (packet_loss_pct and packet_loss_pct > 5):
        if mode == "video":
            mode, q, br, reason = "audio", None, 32, reason + "; high latency/loss → audio"
        elif mode == "audio":
            mode, br, reason = "text", 0, reason + "; high latency/loss → text"
    return {"mode": mode, "video_quality": q, "reason": reason, "max_bitrate_kbps": br}

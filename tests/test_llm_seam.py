import math
import pytest
from typing import Optional, Dict, Any
from pipeline.llm.interface import BaseLLMProvider
from pipeline.text_parser import build_script_with_ai, split_into_segments

class MockLLMProvider(BaseLLMProvider):
    def __init__(self):
        self.call_count = 0
        self.history = []

    def complete(
        self,
        system: str,
        user: str,
        json_schema: Optional[Dict[str, Any]] = None,
        max_tokens: int = 4096
    ) -> Dict[str, Any]:
        self.call_count += 1
        self.history.append({"system": system, "user": user, "json_schema": json_schema})

        import json
        user_data = json.loads(user)
        batch_results = []
        for seg in user_data.get("segments", []):
            seg_id = seg["segment_id"]
            batch_results.append({
                "segment_id": seg_id,
                "voice_steering": f"Steer segment {seg_id}",
                "shots": [
                    {"query": f"Visual B-roll for segment {seg_id}", "source": "library"}
                ]
            })

        return {"batch_results": batch_results}


def test_llm_seam_mock_injection_zero_network_calls():
    mock_provider = MockLLMProvider()
    script_text = "Segment one narration.\n\nSegment two narration.\n\nSegment three narration."
    
    script_json = build_script_with_ai(
        text=script_text,
        title="Test Mock Video",
        series_slug="islamic_history",
        llm_provider=mock_provider,
        batch_size=6
    )

    assert mock_provider.call_count == 1
    assert len(script_json["segments"]) == 3
    assert script_json["segments"][0]["shots"][0]["query"] == "Visual B-roll for segment 1"


def test_chunked_batch_calls_for_52_segments():
    mock_provider = MockLLMProvider()
    
    # Generate 52 narration segments
    segments = [f"This is narration paragraph number {i+1} describing historical events in detail." for i in range(52)]
    script_text = "\n\n".join(segments)

    batch_size = 6
    expected_calls = math.ceil(52 / batch_size)  # 52 / 6 = 9 calls

    script_json = build_script_with_ai(
        text=script_text,
        title="52 Segment Film Test",
        series_slug="islamic_history",
        llm_provider=mock_provider,
        batch_size=batch_size
    )

    assert mock_provider.call_count == expected_calls
    assert len(script_json["segments"]) == 52


def test_narration_verbatim_copy_byte_identical():
    mock_provider = MockLLMProvider()
    
    input_text = (
        "In the year 750 CE, the Abbasid movement reached its climax in Iraq.\n\n"
        "Special characters & quotes: 'Al-Mansur' stated: \"Baghdad shall be built on the Tigris.\"\n\n"
        "Line three with numbers 12345 and punctuation!?..."
    )

    expected_split = split_into_segments(input_text)

    script_json = build_script_with_ai(
        text=input_text,
        title="Verbatim Test",
        series_slug="islamic_history",
        llm_provider=mock_provider,
        batch_size=6
    )

    assert len(script_json["segments"]) == len(expected_split)

    for i, seg_obj in enumerate(script_json["segments"]):
        # Assert byte-identical string match
        assert seg_obj["narration"] == expected_split[i]

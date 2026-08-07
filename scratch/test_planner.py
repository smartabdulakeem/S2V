import os
import sys

# Ensure S2V directory is in python path
S2V_DIR = r"C:\Users\HomePC\Documents\GitHub\S2V"
sys.path.append(S2V_DIR)

from pipeline.ai_agent import generate_storyboard_plan

token = "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"

# Generate a 350 word text
text = (
    "The Grief of Banu Hashim, the Delayed Bai'ah, and the Question of Fatimah. "
    "In the early days of Islamic history, after the passing of the Prophet, deep emotional moments enveloped the household. "
    "The family, known as the Banu Hashim, gathered in quiet mourning, reflection, and discussion. "
    "They debated the transition of leadership and the delay in the pledge of allegiance, known historically as the Delayed Bai'ah. "
    "Scholars and historians have examined these pivotal days to understand the political and spiritual dynamics of the early community. "
    "The questions asked by Fatimah during this period remain central to historical discourse, reflecting her grief and concern for the future. "
    "Each narrative beat represents a complex history that requires careful study, empathy, and documentary storytelling. "
    "We seek to visualize these moments respectfully, focusing on historical realism, soft lighting, and authentic Arabic architecture. "
    "By dividing this script, we can appreciate the nuanced events of each week, from initial grief to political transition and ultimate resolution. "
    "Let us begin our journey through the historical archives of early Baghdad and Medina."
)

print("Running storyboard plan request on chunked script parser...")
res = generate_storyboard_plan(
    text=text,
    title="Ali's Silence",
    voice="edge:en-US-GuyNeural",
    output_filename="test_video",
    visual_style="historical realism, cinematic, soft lighting",
    hf_token=token
)

print("\nResult keys:", list(res.keys()))
print("Fallback:", res.get("fallback"))
if res.get("fallback"):
    print("Error Message:", res.get("error_msg"))
else:
    print(f"Success! Generated {len(res['script']['segments'])} segments via AI chunking.")
    for seg in res["script"]["segments"]:
        print(f"  Scene {seg['segment_id']}: Narration='{seg['narration']}', Prompt='{seg['b_roll_keyword']}'")

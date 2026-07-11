from youtube_transcript_api import YouTubeTranscriptApi

try:
    srt = YouTubeTranscriptApi.get_transcript("Mzua1l4iD4s", languages=["th"])
    text = " ".join([x["text"] for x in srt])
    print("Transcript retrieved successfully:")
    print(text[:1000])
except Exception as e:
    print(f"Error: {e}")

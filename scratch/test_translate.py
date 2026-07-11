from youtube_transcript_api import YouTubeTranscriptApi

def test_trans(video_id):
    try:
        api = YouTubeTranscriptApi()
        t_list = api.list(video_id)
        available = list(t_list)
        if available:
            print(f"Available language: {available[0].language_code}")
            srt = available[0].fetch()
            print("Success fetching native!")
            print(srt[:2])
        else:
            print("No transcripts available")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_trans("Qkc0Bl7NVcY")

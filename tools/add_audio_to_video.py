import argparse
import os
import sys
from moviepy import VideoFileClip, AudioFileClip

def add_audio_to_video(video_path, audio_path, output_path):
    """
    Merges an audio file with a video file, trimming the audio to match the video duration.
    """
    if not os.path.exists(video_path):
        print(f"Error: Video file '{video_path}' not found.")
        return False
    if not os.path.exists(audio_path):
        print(f"Error: Audio file '{audio_path}' not found.")
        return False

    try:
        video = VideoFileClip(video_path)
        audio = AudioFileClip(audio_path)
        
        # Trim audio if it's longer than the video
        if audio.duration > video.duration:
            print(f"Trimming audio from {audio.duration:.2f}s to match video {video.duration:.2f}s")
            audio = audio.subclipped(0, video.duration)
        
        # Attach audio to video
        final_video = video.with_audio(audio)
        
        # Write the result
        print(f"Writing final video to '{output_path}'...")
        final_video.write_videofile(output_path, codec="libx264", audio_codec="aac")
        
        # Close clips to free resources
        video.close()
        audio.close()
        
        print("Success!")
        return True
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="Helper script to add audio to a video file.")
    parser.add_argument("--video", required=True, help="Path to the input MP4 video file")
    parser.add_argument("--audio", required=True, help="Path to the input audio file (mp3, wav, etc.)")
    parser.add_argument("--output", default="output_with_audio.mp4", help="Path for the output video file")

    args = parser.parse_args()
    
    add_audio_to_video(args.video, args.audio, args.output)

if __name__ == "__main__":
    main()

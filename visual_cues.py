"""Visual cue session: the account decides which cues to look for, then the video is inspected for them.

    python visual_cues.py clip.mp4 --latest                 use the most recent logged transcript
    python visual_cues.py clip.mp4 --transcript "He is gasping and his lips look pale"
    python visual_cues.py clip.mp4 --transcript-file account.txt --age 54

Models and frame settings come from inputs/.env. Frames that back a conclusion are saved to
recordings/ and the session is logged to logs/visual_cues.json, like the demo page's Visual cues card.
Decision support only: this is not a diagnosis.
"""
import argparse
import sys
from pathlib import Path

from src.services.cue_log import log_visual_cues
from src.services.recordings import save_recording
from src.services.transcript_log import read_transcripts
from src.services.vqa_evaluator import run_visual_cue_session

MARK = {"present": "PRESENT      ", "absent": "absent       ", "cannot_assess": "cannot assess"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("video", type=Path)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--transcript", help="the bystander's account, as text")
    source.add_argument("--transcript-file", type=Path)
    source.add_argument("--latest", action="store_true", help="use the most recent logged transcript")
    parser.add_argument("--age", type=int)
    args = parser.parse_args()

    if not args.video.exists():
        print(f"File not found: {args.video}", file=sys.stderr)
        return 1
    if args.latest:
        logged = [r for r in read_transcripts(10) if r.get("transcript")]
        transcript = logged[0]["transcript"] if logged else ""
        print(f"Using the latest logged transcript ({len(transcript)} characters).")
    elif args.transcript_file:
        transcript = args.transcript_file.read_text(encoding="utf-8")
    else:
        transcript = args.transcript or ""

    print("Planning from the account, then inspecting the video (this takes a minute)...")
    report, frames = run_visual_cue_session(args.video.read_bytes(), transcript, args.age)

    print("\n1. What the account suggests looking for")
    if report.plan.presentations:
        print(f"   possible kinds of problem: {', '.join(report.plan.presentations)}")
    for cue in report.plan.cues:
        quote = f'  "{cue.transcript_quote}"' if cue.transcript_quote else ""
        print(f"   [{cue.source:10}] {cue.label}{quote}")

    print("\n2. What the video shows")
    for f in report.findings:
        frames_txt = f"  frames {f.evidence_frames}" if f.evidence_frames else ""
        print(f"   {MARK[f.finding]} {f.label} ({f.confidence:.0%}){frames_txt}\n                  {f.reason}")

    if report.reported_but_not_seen:
        print("\n3. Suggested by the account but NOT confirmed by the video")
        for label in report.reported_but_not_seen:
            print(f"   - {label}")

    for issue in report.plan.issues + report.issues:
        print(f"\nNote: {issue}")

    cited = {i for f in report.findings for i in f.evidence_frames}
    files = {fr.index: save_recording("cue-frame", fr.jpeg, "jpg", label=f"{args.video.stem}_f{fr.index}")
             for fr in frames if fr.index in cited}
    log_visual_cues(args.video.name, transcript, report, files)
    if any(files.values()):
        print("\nEvidence frames saved:", ", ".join(u for u in files.values() if u))
    print("\nDecision support only, not a diagnosis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

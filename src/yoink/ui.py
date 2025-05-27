import sys
import time
import threading
from typing import Optional

class Spinner:
    """A simple CLI spinner with a yoinking theme that completes its cycle."""

    def __init__(self, message="Yoinking...", delay=0.15, active_on_tty_only=True):
        self.spinner_frames = [
            "🎣--~       ",
            "🎣---~      ",
            "🎣----~     ",
            "🎣-----~    ",
            "🎣------~   ",
            "🎣-------~  ",
            "🎣--------~ ",
            "🎣--------~🐟",
            "🎣-------🐟 ",
            "🎣------🐟  ",
            "🎣-----🐟   ",
            "🎣----🐟    ",
            "🎣---🐟     ",
            "🎣--🐟      ",
            "🎣-🐟       ",
            "🎣🐟        ",
        ]
        self.delay = delay
        self.base_message = message
        self._running = False
        self._stop_requested = False
        self._cycle_complete_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.active_on_tty_only = active_on_tty_only
        self.is_tty = sys.stdout.isatty()
        self.current_frame_idx = 0
        self._max_spinner_frame_len = max(len(s) for s in self.spinner_frames)

    def _spin(self):
        self.current_frame_idx = 0
        while self._running:
            if self._stop_requested and self.current_frame_idx == 0:
                self._running = False
                self._cycle_complete_event.set()
                break

            spinner_frame = self.spinner_frames[self.current_frame_idx]
            output_line = f"\r{self.base_message} {spinner_frame}"

            padding_len = self._max_spinner_frame_len - len(spinner_frame) + 2
            padding = " " * padding_len
            print(output_line + padding, end="")
            sys.stdout.flush()

            time.sleep(self.delay)
            self.current_frame_idx = (self.current_frame_idx + 1) % len(
                self.spinner_frames
            )

            if self.current_frame_idx == 0 and self._stop_requested:
                self._running = False
                self._cycle_complete_event.set()

    def start(self):
        if self.active_on_tty_only and not self.is_tty:
            print(f"{self.base_message} ...", end="")
            sys.stdout.flush()
            return

        if not self._running:
            self._stop_requested = False
            self._cycle_complete_event.clear()
            self._running = True
            self.current_frame_idx = 0
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()

    def stop(
        self,
        success: bool,
        result_message: Optional[str] = None,
        success_char: str = "🐟",
        failure_char: str = "😫",
    ):
        if self.active_on_tty_only and not self.is_tty:
            if result_message:
                print(f" {result_message}")
            else:
                print(" Done." if success else " Failed.")
            sys.stdout.flush()
            return

        if self._running:
            if not self._stop_requested:
                self._stop_requested = True

            if self._thread and self._thread.is_alive():
                timeout_duration = len(self.spinner_frames) * self.delay + 1.5
                completed_gracefully = self._cycle_complete_event.wait(
                    timeout=timeout_duration
                )
                if not completed_gracefully:
                    self._running = False
                    # Attempt to join briefly, but don't hang indefinitely
                    if self._thread: # Check again as _thread could become None
                        self._thread.join(timeout=0.2)


            clear_line_len = (
                len(self.base_message) + 1 + self._max_spinner_frame_len + 2
            )
            clear_line_str = "\r" + " " * clear_line_len + "\r"
            print(clear_line_str, end="")
            sys.stdout.flush()

        final_char = success_char if success else failure_char
        if result_message:
            print(f"{final_char} {result_message}")
        else:
            default_msg = "Operation complete." if success else "Operation failed."
            print(f"{final_char} {default_msg}")
        sys.stdout.flush()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        is_success = exc_type is None
        exit_message = None
        if not is_success:
            exit_message = "An unexpected error occurred."

        self.stop(
            success=is_success,
            result_message=exit_message,
            success_char="🎉",  # Generic success for context manager
            failure_char="🌊",  # Generic failure for context manager
        )
        # Return False to propagate exceptions if any occurred within the `with` block
        return False
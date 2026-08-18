import os
import re
import subprocess
import sys
import threading
import tkinter as tk

from tkinter import messagebox

from PIL import Image
from PIL import ImageTk

# ================= CONFIGURATION =================
IMAGE_PATH = "vectored-frame.png"
SOURCE_CODE_PATH = "/home/vane/projects/amv/ardupilot/libraries/AP_Motors/AP_Motors6DOF.cpp"
DOCKER_CONTAINER_NAME = "ardupilot_dev_container"
ARDUPILOT_WORKSPACE = "/workspace"

# Coordinates for the input fields on your specific image (x, y)
MOTOR_COORDS = {
    1: (230, 70),  # Top Right
    2: (80, 70),  # Top Left
    5: (230, 160),  # Mid Right (Upper)
    6: (80, 160),  # Mid Left  (Upper)
    3: (230, 340),  # Bottom Right
    4: (80, 340),  # Bottom Left
}

DIMENSIONS = ["Roll", "Pitch", "Yaw", "Throttle", "Forward", "Lateral", "Range"]
# =================================================


class MotorMatrixTuner:
    def __init__(self, root):
        self.root = root
        self.root.title("ArduSub Motor Matrix Tuner")

        # Initialize data structures
        self.matrix_data = {m: {dim: 0.0 for dim in DIMENSIONS if dim != "Range"} for m in MOTOR_COORDS.keys()}
        self.range_data = {m: {"Min": 1300, "Max": 1700} for m in MOTOR_COORDS.keys()}

        self.current_dim = tk.StringVar(value=DIMENSIONS[4])  # Default to Forward
        self.last_dim = self.current_dim.get()

        self.entry_widgets = {}
        self.entry_windows = {}
        self.range_widgets = {}

        # 1. Parse existing values from source code FIRST
        self.read_source_code()

        self._build_top_frame()
        self._build_canvas_frame()
        self._build_bottom_frame()

        # 2. Load the parsed values into the UI entries
        self.load_entries()

    def read_source_code(self):
        """Reads the existing C++ file and extracts matrix/range values before UI launches."""
        if not os.path.exists(SOURCE_CODE_PATH):
            print(f"Warning: {SOURCE_CODE_PATH} not found. Starting with default values.")
            return

        with open(SOURCE_CODE_PATH, "r") as file:
            lines = file.readlines()

        in_custom_matrix = False
        in_range_matrix = False

        for line in lines:
            # Check Matrix bounds
            if "// --- CUSTOM MOTOR MATRIX START ---" in line:
                in_custom_matrix = True
                continue
            elif "// --- CUSTOM MOTOR MATRIX END ---" in line:
                in_custom_matrix = False
                continue

            # Check Range bounds
            if "// --- CUSTOM MOTOR RANGE START ---" in line:
                in_range_matrix = True
                continue
            elif "// --- CUSTOM MOTOR RANGE END ---" in line:
                in_range_matrix = False
                continue

            # Parse Matrix
            if in_custom_matrix and "add_motor_raw_6dof" in line:
                match = re.search(r"\((.*?)\)", line)
                if match:
                    args = match.group(1).split(",")
                    if len(args) >= 7:
                        try:
                            motor_id_str = args[0].strip()
                            motor_id = int(motor_id_str.split("_")[-1])
                            if motor_id in self.matrix_data:

                                def parse_val(val_str):
                                    return float(val_str.strip().replace("f", ""))

                                self.matrix_data[motor_id]["Roll"] = parse_val(args[1])
                                self.matrix_data[motor_id]["Pitch"] = parse_val(args[2])
                                self.matrix_data[motor_id]["Yaw"] = parse_val(args[3])
                                self.matrix_data[motor_id]["Throttle"] = parse_val(args[4])
                                self.matrix_data[motor_id]["Forward"] = parse_val(args[5])
                                self.matrix_data[motor_id]["Lateral"] = parse_val(args[6])
                        except Exception as e:
                            print(f"Error parsing source code matrix line: {line.strip()}\n{e}")

            # Parse Range
            if in_range_matrix:
                if "mot_min" in line:
                    # FIX: Match the array AFTER the equals sign to avoid capturing [6]
                    match = re.search(r"=\s*\{(.*?)\}", line)
                    if match:
                        vals = [int(v.strip()) for v in match.group(1).split(",") if v.strip()]
                        for i, val in enumerate(vals):
                            motor_id = i + 1  # arrays are 0-indexed, motors are 1-indexed
                            if motor_id in self.range_data:
                                self.range_data[motor_id]["Min"] = val
                elif "mot_max" in line:
                    # FIX: Match the array AFTER the equals sign to avoid capturing [6]
                    match = re.search(r"=\s*\{(.*?)\}", line)
                    if match:
                        vals = [int(v.strip()) for v in match.group(1).split(",") if v.strip()]
                        for i, val in enumerate(vals):
                            motor_id = i + 1
                            if motor_id in self.range_data:
                                self.range_data[motor_id]["Max"] = val

    def _build_top_frame(self):
        top_frame = tk.Frame(self.root, pady=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        tk.Label(top_frame, text="Select Dimension:", font=("Arial", 12, "bold")).pack(side=tk.LEFT, padx=10)

        for dim in DIMENSIONS:
            rb = tk.Radiobutton(
                top_frame,
                text=dim,
                variable=self.current_dim,
                value=dim,
                command=self.on_dimension_change,
                font=("Arial", 10, "bold" if dim == "Range" else "normal"),
                fg="blue" if dim == "Range" else "black",
            )
            rb.pack(side=tk.LEFT, padx=5)

    def _build_canvas_frame(self):
        canvas_frame = tk.Frame(self.root)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        try:
            self.bg_image = Image.open(IMAGE_PATH)
            self.bg_photo = ImageTk.PhotoImage(self.bg_image)
            width, height = self.bg_image.size
        except FileNotFoundError:
            width, height = 600, 500
            self.bg_photo = tk.PhotoImage(width=width, height=height)
            print(f"Warning: {IMAGE_PATH} not found. Using blank background.")

        self.canvas = tk.Canvas(canvas_frame, width=width, height=height)
        self.canvas.pack()
        self.canvas.create_image(0, 0, image=self.bg_photo, anchor=tk.NW)

        for motor_id, (x, y) in MOTOR_COORDS.items():
            # FIX: Use native Canvas text and shapes for the Motor ID instead of a tk.Label
            # This prevents UI clipping/layering issues on the image
            self.canvas.create_rectangle(x - 48, y - 18, x, y + 10, fill="white", outline="gray")
            self.canvas.create_text(x - 40, y, text=f"M{motor_id}", font=("Arial", 10, "bold"), fill="black")

            # Standard 6DOF Entry Widget
            ent = tk.Entry(self.canvas, width=6, justify="center")
            win_id = self.canvas.create_window(x + 15, y, window=ent)
            self.entry_widgets[motor_id] = ent
            self.entry_windows[motor_id] = win_id

            # Range Min/Max Widgets (Hidden by default)
            lbl_min = self.canvas.create_text(
                x - 5, y - 14, text="min", font=("Arial", 8, "bold"), state=tk.HIDDEN, fill="darkred"
            )
            ent_min = tk.Entry(self.canvas, width=5, justify="center")
            win_min = self.canvas.create_window(x - 5, y, window=ent_min, state=tk.HIDDEN)

            lbl_max = self.canvas.create_text(
                x + 35, y - 14, text="max", font=("Arial", 8, "bold"), state=tk.HIDDEN, fill="darkgreen"
            )
            ent_max = tk.Entry(self.canvas, width=5, justify="center")
            win_max = self.canvas.create_window(x + 35, y, window=ent_max, state=tk.HIDDEN)

            self.range_widgets[motor_id] = {
                "min": ent_min,
                "max": ent_max,
                "win_min": win_min,
                "win_max": win_max,
                "lbl_min": lbl_min,
                "lbl_max": lbl_max,
            }

    def _build_bottom_frame(self):
        bottom_frame = tk.Frame(self.root, pady=15)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self.run_btn = tk.Button(
            bottom_frame,
            text="Patch Source & Flash (Pixhawk1)",
            font=("Arial", 12, "bold"),
            bg="green",
            fg="white",
            command=self.execute_workflow,
        )
        self.run_btn.pack()

    def on_dimension_change(self):
        """Triggered when the radio button changes. Saves current view, switches, and loads new view."""
        self.save_entries()
        self.last_dim = self.current_dim.get()
        self.load_entries()

    def save_entries(self):
        if self.last_dim == "Range":
            for m, w in self.range_widgets.items():
                try:
                    self.range_data[m]["Min"] = int(w["min"].get())
                    self.range_data[m]["Max"] = int(w["max"].get())
                except ValueError:
                    pass
        else:
            for motor_id, ent in self.entry_widgets.items():
                try:
                    self.matrix_data[motor_id][self.last_dim] = float(ent.get())
                except ValueError:
                    pass

    def load_entries(self):
        dim = self.current_dim.get()

        if dim == "Range":
            for m in MOTOR_COORDS.keys():
                # Hide standard entry
                self.canvas.itemconfigure(self.entry_windows[m], state=tk.HIDDEN)

                # Show min/max entries and labels
                self.canvas.itemconfigure(self.range_widgets[m]["win_min"], state=tk.NORMAL)
                self.canvas.itemconfigure(self.range_widgets[m]["win_max"], state=tk.NORMAL)
                self.canvas.itemconfigure(self.range_widgets[m]["lbl_min"], state=tk.NORMAL)
                self.canvas.itemconfigure(self.range_widgets[m]["lbl_max"], state=tk.NORMAL)

                # Populate min/max data
                self.range_widgets[m]["min"].delete(0, tk.END)
                self.range_widgets[m]["min"].insert(0, str(self.range_data[m]["Min"]))
                self.range_widgets[m]["max"].delete(0, tk.END)
                self.range_widgets[m]["max"].insert(0, str(self.range_data[m]["Max"]))
        else:
            for m in MOTOR_COORDS.keys():
                # Show standard entry
                self.canvas.itemconfigure(self.entry_windows[m], state=tk.NORMAL)

                # Hide min/max entries and labels
                self.canvas.itemconfigure(self.range_widgets[m]["win_min"], state=tk.HIDDEN)
                self.canvas.itemconfigure(self.range_widgets[m]["win_max"], state=tk.HIDDEN)
                self.canvas.itemconfigure(self.range_widgets[m]["lbl_min"], state=tk.HIDDEN)
                self.canvas.itemconfigure(self.range_widgets[m]["lbl_max"], state=tk.HIDDEN)

                # Populate 6DOF data
                self.entry_widgets[m].delete(0, tk.END)
                self.entry_widgets[m].insert(0, str(self.matrix_data[m][dim]))

    def generate_matrix_code(self):
        code_lines = []
        for i in sorted(MOTOR_COORDS.keys()):
            d = self.matrix_data[i]
            line = (
                f"    add_motor_raw_6dof(AP_MOTORS_MOT_{i}, "
                f"{d['Roll']}f, {d['Pitch']}f, {d['Yaw']}f, "
                f"{d['Throttle']}f, {d['Forward']}f, {d['Lateral']}f, {i});"
            )
            code_lines.append(line)
        return "\n".join(code_lines) + "\n"

    def generate_range_code(self):
        min_vals = []
        max_vals = []
        # Construct arrays for motors 1-6
        for i in range(1, 7):
            if i in self.range_data:
                min_vals.append(str(self.range_data[i]["Min"]))
                max_vals.append(str(self.range_data[i]["Max"]))
            else:
                # Provide safe defaults if a motor id is somehow missing
                min_vals.append("1300")
                max_vals.append("1700")

        min_str = ", ".join(min_vals)
        max_str = ", ".join(max_vals)

        # Matches exactly how it appeared in your source C++ script
        return f"  const int mot_min[6] = {{ {min_str} }};\n  const int mot_max[6] = {{ {max_str} }};\n"

    def execute_workflow(self):
        # Force a save of whatever view is currently active
        self.save_entries()

        self.run_btn.config(state=tk.DISABLED, text="Running...")

        try:
            self.patch_source_code()
        except Exception as e:
            messagebox.showerror("File Error", f"Failed to patch source:\n{e}")
            self.run_btn.config(state=tk.NORMAL, text="Patch Source & Flash")
            return

        threading.Thread(target=self.run_docker_exec, daemon=True).start()

    def patch_source_code(self):
        if not os.path.exists(SOURCE_CODE_PATH):
            print(f"Warning: {SOURCE_CODE_PATH} not found. Skipping file write for testing.")
            print("Generated Matrix Code:\n" + self.generate_matrix_code())
            print("Generated Range Code:\n" + self.generate_range_code())
            return

        with open(SOURCE_CODE_PATH, "r") as file:
            lines = file.readlines()

        mat_start_idx, mat_end_idx = -1, -1
        rng_start_idx, rng_end_idx = -1, -1

        for i, line in enumerate(lines):
            if "// --- CUSTOM MOTOR MATRIX START ---" in line:
                mat_start_idx = i
            elif "// --- CUSTOM MOTOR MATRIX END ---" in line:
                mat_end_idx = i
            elif "// --- CUSTOM MOTOR RANGE START ---" in line:
                rng_start_idx = i
            elif "// --- CUSTOM MOTOR RANGE END ---" in line:
                rng_end_idx = i

        if (mat_start_idx == -1 or mat_end_idx == -1) and (rng_start_idx == -1 or rng_end_idx == -1):
            raise ValueError("Could not find start/end markers for Matrix or Range in the C++ file.")

        # Replace text blocks from bottom to top so index numbers don't shift during patching
        blocks_to_patch = []
        if rng_start_idx != -1 and rng_end_idx != -1:
            blocks_to_patch.append((rng_start_idx, rng_end_idx, self.generate_range_code()))
        if mat_start_idx != -1 and mat_end_idx != -1:
            blocks_to_patch.append((mat_start_idx, mat_end_idx, self.generate_matrix_code()))

        # Sort blocks by start index descending (bottom up)
        blocks_to_patch.sort(key=lambda x: x[0], reverse=True)

        for start_idx, end_idx, new_code in blocks_to_patch:
            lines = lines[: start_idx + 1] + [new_code] + lines[end_idx:]

        with open(SOURCE_CODE_PATH, "w") as file:
            file.writelines(lines)

        print("Successfully patched C++ source code.")

    def run_docker_exec(self):
        print("\n" + "=" * 50)
        print("Starting Docker Compile and Upload (New Container)...")
        print("=" * 50 + "\n")

        cmd = [
            "docker",
            "run",
            "--rm",
            "-i",
            "--privileged",
            "-v",
            "/dev:/dev",
            "--network=host",
            "-v",
            "/home/vane/projects/amv/ardupilot:/workspace",
            "-w",
            "/workspace",
            "ardupilot/ardupilot-dev-chibios:sha-f7612cba",
            "bash",
            "-c",
            "git config --global --add safe.directory '*' && ./waf configure --board Pixhawk1 && ./waf sub --upload",
        ]

        try:
            process = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr, text=True)
            process.wait()

            if process.returncode == 0:
                print("\n✅ Firmware compiled and uploaded successfully!")
            else:
                print(f"\n❌ Docker exited with code {process.returncode}")

        except Exception as e:
            print(f"\n❌ Failed to run Docker command: {e}")
        finally:
            self.root.after(0, lambda: self.run_btn.config(state=tk.NORMAL, text="Patch Source & Flash"))


if __name__ == "__main__":
    root = tk.Tk()
    app = MotorMatrixTuner(root)
    root.mainloop()

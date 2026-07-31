import os
import re  # Added for parsing source code
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
ARDUPILOT_WORKSPACE = "/workspace"  # Path inside the docker container


# Coordinates for the input fields on your specific image (x, y)
MOTOR_COORDS = {
    1: (230, 70),  # Top Right
    2: (80, 70),  # Top Left
    5: (230, 160),  # Mid Right (Upper)
    6: (80, 160),  # Mid Left  (Upper)
    3: (230, 340),  # Bottom Right
    4: (80, 340),  # Bottom Left
}

DIMENSIONS = ["Roll", "Pitch", "Yaw", "Throttle", "Forward", "Lateral"]
# =================================================


class MotorMatrixTuner:
    def __init__(self, root):
        self.root = root
        self.root.title("ArduSub Motor Matrix Tuner")

        # Initialize data structure holding motors x 6 DOFs
        self.matrix_data = {m: {dim: 0.0 for dim in DIMENSIONS} for m in MOTOR_COORDS.keys()}

        self.current_dim = tk.StringVar(value=DIMENSIONS[4])  # Default to Forward
        self.entry_widgets = {}

        # 1. Parse existing values from source code FIRST
        self.read_source_code()

        self._build_top_frame()
        self._build_canvas_frame()
        self._build_bottom_frame()

        # 2. Load the parsed values into the UI entries
        self.load_entries()

    def read_source_code(self):
        """Reads the existing C++ file and extracts matrix values before UI launches."""
        if not os.path.exists(SOURCE_CODE_PATH):
            print(f"Warning: {SOURCE_CODE_PATH} not found. Starting with default 0.0 values.")
            return

        with open(SOURCE_CODE_PATH, "r") as file:
            lines = file.readlines()

        in_custom_matrix = False
        for line in lines:
            if "// --- CUSTOM MOTOR MATRIX START ---" in line:
                in_custom_matrix = True
                continue
            elif "// --- CUSTOM MOTOR MATRIX END ---" in line:
                break

            if in_custom_matrix and "add_motor_raw_6dof" in line:
                # Extract the arguments between parentheses
                match = re.search(r"\((.*?)\)", line)
                if match:
                    args = match.group(1).split(",")
                    if len(args) >= 7:
                        try:
                            # Parse Motor ID (e.g., "AP_MOTORS_MOT_1" -> 1)
                            motor_id_str = args[0].strip()
                            motor_id = int(motor_id_str.split("_")[-1])

                            if motor_id in self.matrix_data:
                                # Helper to remove 'f' suffix and convert to float
                                def parse_val(val_str):
                                    return float(val_str.strip().replace("f", ""))

                                self.matrix_data[motor_id]["Roll"] = parse_val(args[1])
                                self.matrix_data[motor_id]["Pitch"] = parse_val(args[2])
                                self.matrix_data[motor_id]["Yaw"] = parse_val(args[3])
                                self.matrix_data[motor_id]["Throttle"] = parse_val(args[4])
                                self.matrix_data[motor_id]["Forward"] = parse_val(args[5])
                                self.matrix_data[motor_id]["Lateral"] = parse_val(args[6])
                        except Exception as e:
                            print(f"Error parsing source code line: {line.strip()}\n{e}")

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
                font=("Arial", 10),
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
            lbl = tk.Label(self.canvas, text=f"M{motor_id}", bg="white")
            self.canvas.create_window(x - 30, y, window=lbl)

            ent = tk.Entry(self.canvas, width=6, justify="center")
            self.canvas.create_window(x + 15, y, window=ent)
            self.entry_widgets[motor_id] = ent

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
        self.save_entries()
        self.load_entries()

    def save_entries(self):
        pass

    def load_entries(self):
        dim = self.current_dim.get()
        for motor_id, ent in self.entry_widgets.items():
            ent.delete(0, tk.END)
            ent.insert(0, str(self.matrix_data[motor_id][dim]))

    last_dim = DIMENSIONS[4]

    def on_dimension_change(self):
        for motor_id, ent in self.entry_widgets.items():
            try:
                val = float(ent.get())
                self.matrix_data[motor_id][self.last_dim] = val
            except ValueError:
                pass

        self.last_dim = self.current_dim.get()
        self.load_entries()

    def generate_cpp_code(self):
        self.on_dimension_change()

        code_lines = []
        # Dynamically loop through the motors actually defined in MOTOR_COORDS
        for i in sorted(MOTOR_COORDS.keys()):
            d = self.matrix_data[i]
            # Use add_motor_raw_6dof and append 'f' to floats to match C++ syntax
            line = (
                f"    add_motor_raw_6dof(AP_MOTORS_MOT_{i}, "
                f"{d['Roll']}f, {d['Pitch']}f, {d['Yaw']}f, "
                f"{d['Throttle']}f, {d['Forward']}f, {d['Lateral']}f, {i});"
            )
            code_lines.append(line)
        return "\n".join(code_lines) + "\n"

    def execute_workflow(self):
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
            print("Generated Code:\n" + self.generate_cpp_code())
            return

        with open(SOURCE_CODE_PATH, "r") as file:
            lines = file.readlines()

        start_idx = -1
        end_idx = -1
        for i, line in enumerate(lines):
            if "// --- CUSTOM MOTOR MATRIX START ---" in line:
                start_idx = i
            elif "// --- CUSTOM MOTOR MATRIX END ---" in line:
                end_idx = i

        if start_idx != -1 and end_idx != -1:
            new_code = self.generate_cpp_code()
            lines = lines[: start_idx + 1] + [new_code] + lines[end_idx:]

            with open(SOURCE_CODE_PATH, "w") as file:
                file.writelines(lines)
            print("Successfully patched C++ source code.")
        else:
            raise ValueError("Could not find start/end markers in the C++ file.")

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

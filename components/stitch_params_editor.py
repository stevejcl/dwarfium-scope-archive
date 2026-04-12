from nicegui import ui
from api.dwarf_backup_db_api import get_setting_text, set_setting_text
import json

# DB key: "STITCH_PARAMS"
# Value: JSON string
STITCH_PARAMS_DEFAULT = {
    "alignment": {
        "detection_sigma":      2,
        "max_control_points":   100,
        "align_pad":            0.20,
        "asinh_factor":         10,
        "bg_blur_ksize":        101,
        "max_size":             2048
    },
    "blending": {
        "feather_size":         51,
        "crop_tolerance":       5
    },
    "stacking": {
        "method":               "weighted",   # mean / median / sigma_clip / weighted
        "sigma":                2.5
    }
}

def get_stitch_params(conn) -> dict:
    """Load stitch params from DB, fallback to defaults if not set."""
    raw = get_setting_text(conn, "STITCH_PARAMS")
    if not raw:
        return STITCH_PARAMS_DEFAULT.copy()
    try:
        stored = json.loads(raw)
        # Deep merge — fills missing keys with defaults
        result = STITCH_PARAMS_DEFAULT.copy()
        for group, values in stored.items():
            if group in result:
                result[group].update(values)
        return result
    except Exception:
        return STITCH_PARAMS_DEFAULT.copy()

def save_stitch_params(conn, params: dict):
    set_setting_text(conn, "STITCH_PARAMS", json.dumps(params))

class StitchParamsEditor:
    def __init__(self, conn, on_change=None):
        """
        conn      : DB connection (to load/save)
        on_change : optional callback(params) called when params change
                    if None → shows Save button (Settings mode)
                    if set  → live update to caller (dialog mode)
        """
        self.conn = conn
        self.on_change = on_change
        self.params = get_stitch_params(conn)
        self.build_ui()

    def build_ui(self):
        p = self.params
        a = p["alignment"]
        b = p["blending"]
        s = p["stacking"]

        with ui.card().classes("p-4 gap-3 w-full"):
            ui.label("🔭 Stitch Parameters").classes("text-lg font-semibold")

            # --- Alignment ---
            with ui.expansion("🎯 Alignment", value=True).classes("w-full"):
                with ui.grid(columns=2).classes("w-full gap-2"):
                    self.detection_sigma = ui.number("Detection sigma", value=a["detection_sigma"], min=1, max=10, step=0.5)
                    self.max_control_points = ui.number("Max control points", value=a["max_control_points"], min=10, max=500, step=10)
                    self.align_pad = ui.number("Alignment padding", value=a["align_pad"], min=0, max=0.5, step=0.05, format="%.2f")
                    self.max_size = ui.number("Max size for alignment", value=a["max_size"], min=512, max=4096, step=256)
                with ui.grid(columns=2).classes("w-full gap-2"):
                    self.asinh_factor = ui.number("Asinh stretch factor", value=a["asinh_factor"], min=1, max=50, step=1)
                    self.bg_blur_ksize = ui.number("Background blur kernel", value=a["bg_blur_ksize"], min=11, max=301, step=10)

            # --- Blending ---
            with ui.expansion("🎨 Blending", value=True).classes("w-full"):
                with ui.grid(columns=2).classes("w-full gap-2"):
                    self.feather_size = ui.number("Feather size", value=b["feather_size"], min=0, max=200, step=10)
                    self.crop_tolerance = ui.number("Crop tolerance", value=b["crop_tolerance"], min=0, max=20, step=1)

            # --- Stacking ---
            with ui.expansion("📚 Stacking", value=True).classes("w-full"):
                with ui.grid(columns=2).classes("w-full gap-2"):
                    self.stack_method = ui.select(
                        ["mean", "median", "sigma_clip", "weighted"],
                        label="Stack method",
                        value=s["method"]
                    )
                    self.sigma = ui.number("Sigma clip", value=s["sigma"], min=1.0, max=5.0, step=0.1, format="%.1f")

            # --- Buttons ---
            with ui.row().classes("justify-end gap-2 mt-2"):
                ui.button("↺ Reset defaults", on_click=self.reset_defaults).props("flat")
                if self.on_change:
                    # Dialog mode — Apply button
                    ui.button("✅ Apply", on_click=self.apply).props("color=positive")
                else:
                    # Settings page mode — Save to DB
                    ui.button("💾 Save", on_click=self.save).props("color=positive")

    def _collect(self) -> dict:
        """Read current UI values into params dict."""
        return {
            "alignment": {
                "detection_sigma":    self.detection_sigma.value,
                "max_control_points": self.max_control_points.value,
                "align_pad":          self.align_pad.value,
                "asinh_factor":       self.asinh_factor.value,
                "bg_blur_ksize":      int(self.bg_blur_ksize.value),
                "max_size":           int(self.max_size.value),
            },
            "blending": {
                "feather_size":   int(self.feather_size.value),
                "crop_tolerance": int(self.crop_tolerance.value),
            },
            "stacking": {
                "method": self.stack_method.value,
                "sigma":  self.sigma.value,
            }
        }

    def apply(self):
        """Dialog mode — notify caller with current params."""
        self.params = self._collect()
        if self.on_change:
            self.on_change(self.params)
        ui.notify("✅ Parameters applied for this run", type="positive")

    def save(self):
        """Settings mode — persist to DB."""
        self.params = self._collect()
        save_stitch_params(self.conn, self.params)
        ui.notify("✅ Stitch parameters saved", type="positive")

    def reset_defaults(self):
        """Reset UI to default values."""
        d = STITCH_PARAMS_DEFAULT
        self.detection_sigma.value    = d["alignment"]["detection_sigma"]
        self.max_control_points.value = d["alignment"]["max_control_points"]
        self.align_pad.value          = d["alignment"]["align_pad"]
        self.asinh_factor.value       = d["alignment"]["asinh_factor"]
        self.bg_blur_ksize.value      = d["alignment"]["bg_blur_ksize"]
        self.max_size.value           = d["alignment"]["max_size"]
        self.feather_size.value       = d["blending"]["feather_size"]
        self.crop_tolerance.value     = d["blending"]["crop_tolerance"]
        self.stack_method.value       = d["stacking"]["method"]
        self.sigma.value              = d["stacking"]["sigma"]
        ui.notify("↺ Reset to defaults", type="info")
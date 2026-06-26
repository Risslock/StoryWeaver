"""Side-effect import: installs warning filters before Gradio/Starlette are imported.

Import this module first in any entry-point (app.py, main.py) to suppress
third-party deprecation noise that we cannot fix upstream.
"""

import warnings

# Gradio 6.x references the old Starlette constant name; suppress until Gradio ships a fix.
warnings.filterwarnings(
    "ignore",
    message=".*HTTP_422_UNPROCESSABLE_ENTITY.*",
)

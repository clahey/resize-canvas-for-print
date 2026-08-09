from unittest.mock import MagicMock, patch

import pytest

from test_support import rcfp


@pytest.fixture
def mock_gimp():
    """Patches Gimp/GLib/Gegl at module level so plugin code can run
    outside a real GIMP process. Constructing a real GLib.Error() or a
    Gimp.PlugIn subclass outside an actual plugin process hard-aborts the
    interpreter (not a catchable exception) - sentinel RunMode/PDBStatusType
    values sidestep this."""
    mock = MagicMock()
    mock.RunMode.INTERACTIVE = "INTERACTIVE"
    mock.RunMode.WITH_LAST_VALS = "WITH_LAST_VALS"
    mock.RunMode.NONINTERACTIVE = "NONINTERACTIVE"
    mock.PDBStatusType.SUCCESS = "SUCCESS"
    mock.PDBStatusType.CANCEL = "CANCEL"
    with patch.object(rcfp, "Gimp", mock), \
            patch.object(rcfp, "GLib"), \
            patch.object(rcfp, "Gegl"):
        yield mock


@pytest.fixture
def run_plugin(mock_gimp):
    """Runs ResizeCanvasForPrint.run as an unbound function - self is
    never referenced in its body, and instantiating Gimp.PlugIn outside a
    real GIMP process hard-aborts the interpreter."""

    def _run(image, config, run_mode):
        procedure = MagicMock()
        rcfp.ResizeCanvasForPrint.run(None, procedure, run_mode, image, [], config, None)
        return procedure

    return _run

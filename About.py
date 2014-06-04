# -*- coding: utf-8 -*-
"""Contains details about the GDSC OMERO python scripts"""

import omero.scripts as scripts

if __name__ == "__main__":
    """
    The main entry point of the script, as called by the client via the
    scripting service, passing the required parameters.
    """
    client = scripts.client('About', """\
All the scripts in this directory have been developed by the Genome Damage
and Stability Centre (GDSC) at the University of Sussex.

See: http://www.sussex.ac.uk/gdsc/intranet/microscopy/omero/scripts""",
        version="1.0",
        authors=["Alex Herbert", "GDSC"],
        institutions=["University of Sussex"],
        contact="a.herbert@sussex.ac.uk",
    )  # noqa

OMERO User Scripts
==================

Installation
------------

1. Change into the scripts location of your OMERO installation

        cd OMERO_DIST/lib/scripts

2. Clone the repository with a unique name (e.g. "useful_scripts")

        git clone https://github.com/THISREPOSITORY/omero-user-scripts.git UNIQUE_NAME

3. Update your list of installed scripts by examining the list of scripts
   in OMERO.insight or OMERO.web, or by running the following command

        path/to/bin/omero script list

4. The ImageJ analysis scripts require additional configuration. The scripts
   need to know where to locate the ImageJ program and ImageJ must have the
   correct plugins installed. 

   Additional steps for headless execution of ImageJ on UNIX platforms are
   also required.

   Further details are available in the [INSTALL](INSTALL) file.

Upgrading
---------

1. Change into the repository location cloned into during installation

        cd OMERO_DIST/lib/scripts/UNIQUE_NAME

2. Update the repository to the latest version

        git pull --rebase

3. Update your list of installed scripts by examining the list of scripts
   in OMERO.insight or OMERO.web, or by running the following command

        path/to/bin/omero script list

Developer Installation
----------------------

1. Fork [omero-user-scripts](https://github.com/ome/omero-user-scripts/fork) in your own GitHub account

2. Change into the scripts location of your OMERO installation

        cd OMERO_DIST/lib/scripts

3. Clone the repository

        git clone git@github.com:YOURGITUSER/omero-user-scripts.git YOUR_SCRIPTS

4. The ImageJ analysis scripts require additional configuration. Further details 
   are available in the [INSTALL](INSTALL) file.

Adding a script
---------------

1. Choose a naming scheme for your scripts. The name of the clone
   (e.g. "YOUR_SCRIPTS"), the script name, and all sub-directories will be shown
   to your users in the UI, so think about script organization upfront.

   a. If you don't plan to have many scripts, then you need not have any sub-directories
      and can place scripts directly under YOUR_SCRIPTS.

   b. Otherwise, create a suitable sub-directory. Examples of directories in use can be
      found in the [official scripts](https://github.com/ome/scripts) repository.

2. Place your script in the chosen directory:
  * If you have an existing script, simply save it.
  * Otherwise, copy [Example.txt](Example.txt) and edit it in place. (Don't use git mv)

3. Add the file to git, commit, and push.

Testing your script
-------------------

1. List the current scripts in the system

        path/to/bin/omero script list

2. List the parameters

        path/to/bin/omero script params SCRIPT_ID

3. Launch the script

        path/to/bin/omero script launch SCRIPT_ID

4. See the [developer documentation](https://www.openmicroscopy.org/site/support/omero4/developers/scripts/)
   for more information on testing and modifying your scripts.

Legal
-----

See [LICENSE](LICENSE)


# About #
This section provides machine-readable information about your scripts.
It will be used to help generate a landing page and links for your work.
Please modify **all** values on **each** branch to describe your scripts.

###### Repository name ######
GDSC OMERO User Scripts repository

###### Minimum version ######
4.4

###### Maximum version ######
5.0

###### Owner(s) ######
Alex Herbert

###### Institution ######
Genome Damage and Stability Centre, University of Sussex

###### URL ######
http://www.sussex.ac.uk/gdsc/intranet/microscopy/omero/scripts

###### Email ######
a.herbert@sussex.ac.uk

###### Description ######
Example script repository to be cloned, modified, and extended. 

The scripts contain examples of utility scripts and image analysis using ImageJ.

The following scripts are available:
- Check Images : Check the final frame of an image contains pixel data. Used to 
validate data import completed
- New Images From ROIs : Allows cropping an image, optionally through the z/t 
stack, using ROIs
- Image Size : Produce a report showing the size of images including archives
- Correlation Analyser : Produces a report of an all-vs-all channel correlation
- Coloclisation Analyser : Uses the Confined Displacement Algorithm (CDA) to 
determine if the correlation between two channels is significant. This is done
by comparison with random images created by shifting the pixels within a 
confined region

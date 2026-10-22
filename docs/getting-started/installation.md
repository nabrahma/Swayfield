# Installation

Swayfield is a Blender extension. It needs **Blender 4.5 LTS or newer**. The test suite runs on Blender 4.5 LTS and 5.2 LTS in CI.

It needs no other software, no pip packages and no internet connection.

## Install from a zip

1. Go to [GitHub Releases](https://github.com/nabrahma/Swayfield/releases) and download the latest zip. Do not unzip it.
2. In Blender, open **Edit > Preferences > Get Extensions**.
3. Open the dropdown menu at the top right and choose **Install from Disk**.
4. Pick the zip. (You can also drag the zip into the Blender window.)
5. Make sure the Swayfield checkbox is on.

Open any 3D Viewport and press `N`. You should see a **Swayfield** tab in the sidebar.

!!! note "Offline install"
    Blender may ask about online access when you open Get Extensions. You can say no. Install from Disk works offline.

## Update

Install the newer zip the same way. Blender replaces the old version. Your .blend files keep working, and any layer made with an older version can be moved forward with **Upgrade Layer**.

## Uninstall

Open **Edit > Preferences > Get Extensions**, find Swayfield and remove it. Files you made with Swayfield still open and render, because the node groups and materials are stored in the .blend.

## For developers

To work on Swayfield itself, point Blender at the `swayfield/` folder in the repository: symlink it into a local extension repository, or add a local extension repository in **Preferences > Get Extensions > Repositories** that points at it. See [Contributing](contributing.md).

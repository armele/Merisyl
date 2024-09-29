# Tiled Game Map Walkthrough
For detailed, large roleplaying game maps an improved player experience might be achieved by making it available to your players in a "Google-maps" style of zoomable map, allowing them to see the full detail of your map while still having good browsing performance. 

An example can be found on the [Merisyl Gazette](https://new.merisyl.com/gazette/), which is an ongoing work in progress for my Pathfinder 2E campaign world.

This walkthrough shares one approach for achieiving this. This is not an original idea by any means, and what I've done builds on a variety of sources (listed below). 

## Tools Used:
* [Worldographer](https://worldographer.com/) (map creation): 
* [Gimp](https://www.gimp.org/) (image manipulation): 
* [LeafletJS](https://leafletjs.com/index.html) (map display): 

## High Level Overview: 
1. Create your map  
2. Break your single map file down into small "tiles" that can be pieced together for a smooth
3. Configure Leaflet in an HTML page to point to your tile set.

## Step By Step
### Create Your Map

See the various tutorials available from https://worldographer.com/, or use your preferred map making software.
Export the map to any supported image format.  Note that the tiling step requires a square map, with the dimensions a multiple of 256 pixels. If the map does not meet this criteria, the tiling step below will create a border around the map to bring it into compliance with this requirement (**"tilebase image"**).

### Break Map Into Tiles

There are a variety of tiling solutions out there, but I wanted one specifically that I could use from Gimp, so that I wouldn't have to pay for Photoshop or learn another image editing tool. I ended up rewriting a Gimp plugin I found to improve performance.  This is available here: https://github.com/armele/Merisyl/blob/master/Gimp%20Maptile%20Plugin/Tilemaker.py

Note that I have not overcome Python threading limitations within Gimp, so for large files the plugin will apear stuck (no GUI updates) for a significant amount of time, but if you look at the output folders you'll see your tiles happily being produced.

Install it to Gimp by copying the Tilemaker.py file to your gimp plug-ins directory (for example "C:\Program Files\GIMP 2\lib\gimp\2.0\plug-ins").  

Open your map image in Gimp, and from the menu choose **Filters->Tilemaker->Make Map Tiles**.

You will be prompted for:
* A folder into which the tiled images will be placed ("target folder").  For performance reasons, I suggest a local directory as opposed to a network drive. They may be copied later to somewhere internet-accessible for use in step 3.
* The maximum zoom level for the map. 
* The number of threads to dedicate to this task. You will want to experiement with what your system is capable of supporting. Counterintuitively, the higher the thread count the less frequently the progress will update, and the more likely you are to think something is "stuck".  Four to six seems a decent balance.
* Whether or not you want to skip checking existing tiles for changes (useful for restarting an interrupted job where you know nothing has changed since the last run). If you know you have updated the image file you're tiling, pick "no". Each tile will have its hash compared, and only tiles in the image which have changed will be regenerated. If you know nothing has changed and you just want to restart an interrupted job, pick "yes".

This task may take quite a while, depending on your map size and system capabilities. At the end of this process in your target directory you will have a series of subfolders with the scaled tiles to be used for each zoom level. You will also have the **tilebase image** - a version of your source image that has been centered in a square with sides divisible by 256.

If the process is interrupted it can be restarted without losing progress, assuming you use the same target directory and do not remove the tiles already created. A file called "config.json" will be created in the selected output directory, and this records information that allows the restart to be more efficient. It can be a useful way to see the detail of how the tiling is progressing. I recommend you keep this file with your tile directory structure for speed of future updates.

If you are generating tiles into an existing directory, the plugin is smart enough to compare the existing image to the new one, and overwrite the tile only when necessary.  This means after the initial map creation, updates can be done reasonably quickly.

You may want to copy these into an s3 bucket for use. One way to do this (with the AWS CLI installed) could be, from "target folder":
* aws s3 sync . s3_destination_bucket

### Configure an HTML Page
Knowing that I wanted to host this on a Wordpress site, I first investigated the Wordpress Leaflet Map plugin (https://wordpress.org/plugins/leaflet-map/).  It is an excellent plugin, but designed for real-world scenarios, and ultimately did not give me exactly what I wanted.  I ended up coding the Leaflet JavaScript directly.  The following explanation is based on the [merisylMap.html](https://github.com/armele/Merisyl/blob/master/Gimp%20Maptile%20Plugin/merisylMap.html) (which you're welcome to use as the basis for your own customization).  It requires also that [tiledFantasyMap.js](https://github.com/armele/Merisyl/blob/master/Gimp%20Maptile%20Plugin/tiledFantasyMap.js) be present in the same location.

My criteria were that the map was served up using tiles, that the scale was correct for the map, and that the latitude and longitude markers corresponded to the pixels of the underlying map.

Here are the steps needed to repurpose this HTML for your own map:
* Find the "Basic Customizations" section of the html file.
* Update "referencesize" to the side length of your **tilebase image**.
* Update "metersPerPixel" to indicate the geographic length in meters of one pixel on your **tilebase image**.
* Update "mapLocation" to where your tile folders were created. I am hosting mine in Wordpress, but intend to move them to Amazon S3. If you are using this map locally only, this can be a drive location with a path relative to the location of the .HTML file.
* Comment out (or replace) the contents of locatonsList. These are entries of points of interest, using the [GEOJSON](https://geojson.org/) format supported by Leaflet.

### Referencing the HTML From Wordpress
Install the "Simple IFrame" WordPress plugin.
On the WordPress page you'd like to display the map, insert the page element for the Simple IFrame.
Set the "IFRAME URL" configuration setting to the location of your HTML file.  (I'm using S3.)

### Making Mouseovers:
If you want a walk-through on how to create areas of interest on the map that are highlighted when you mouse-over them and can hyperlink to a detail page, contact me on Discord: [al_mele](https://discordapp.com/channels/@me/al_mele/).  I'm happy to do it, but only if someone will actually read it. :)  It is a bit kludgey now, as it is just used by me.

## Improvements Not Yet Implemented:
* In the HTML, create error handling for bad GEOJSON formatting.

## Credits:
* Similar guide: https://techtrail.net/creating-an-interactive-map-with-leaflet-js/
* Wordpress Leaflet Map Plugin source code: https://github.com/bozdoz/wp-plugin-leaflet-map/tree/master
* Original non-threaded gimp plugin for tiling: https://bitbucket.org/zmasek/gimp-leaflet/src/master/README.rst
* Leaflet Documentation: https://leafletjs.com/
* Python threading overview: https://realpython.com/intro-to-python-threading/
* GIMP Plugin tutorial: https://medium.com/@nerudaj/getting-started-writing-python-plugins-for-gimp-50631ea084cc
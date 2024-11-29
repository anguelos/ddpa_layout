#!/usr/bin/env python3

from collections import defaultdict
import glob
from typing import List, Tuple, Union
import numpy as np
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from pathlib import Path

from lxml import etree
import fargv
import sys


class MapRenderer:
    @staticmethod
    def load_location_data(fsdb_root):    
        def extract_location(archive_xml_path):
            tree = etree.parse(open(archive_xml_path, 'r'))
            ns = {
                'atom': 'http://www.w3.org/2005/Atom',
                'eag': 'http://www.archivgut-online.de/eag'
            }    
            # Find the <eag:location> element and extract latitude and longitude
            location = tree.xpath('//eag:location', namespaces=ns)
            if location:
                latitude = location[0].get('latitude')
                longitude = location[0].get('longitude')
                return latitude, longitude
            return -1, -1
        archive_files = Path(fsdb_root).glob('*/AR.eag.xml')
        archive_to_locations = defaultdict(lambda: (47.0679, 15.4417))
        for archive_file in archive_files:
            latitude, longitude = extract_location(archive_file)
            if latitude and longitude:
                archive_to_locations[archive_file.parent.name] = float(latitude), float(longitude)
            else:
                raise ValueError(f"Could not extract location from {archive_file}")
        return archive_to_locations

    def __init__(self, extent=[-10.0, 40.0, 35.0, 70.0], image_shape=(800, 1000), fsdb_root=None, charter_glob=None):
        self.extent = extent
        self.image_shape = image_shape
        if fsdb_root is not None:
            self.archive_to_locations = self.load_location_data(fsdb_root)
        else:
            self.archive_to_locations = {}
        if charter_glob is not None:
            print(charter_glob)
            charters = glob.glob(charter_glob)
            charters = [ch.split("/") for ch in charters]
            self.charter_locations = {ch[-1]: self.archive_to_locations[ch[-3]] for ch in charters}
        else:
            self.charter_locations = {}
        
    def location2pixels(self, lat: float, lon: float):
        """
        Convert geographic coordinates to pixel coordinates on an image.
        
        Parameters:
        - lat (float): Latitude of the point.
        - lon (float): Longitude of the point.

        Returns:
        - tuple: (row, col) pixel coordinates.
        """
        lon_min, lon_max, lat_min, lat_max = self.extent
        nrows, ncols = self.image_shape[:2]
        
        # Normalize coordinates
        lon_pixel = ((lon - lon_min) / (lon_max - lon_min)) * ncols
        lat_pixel = ((lat_max - lat) / (lat_max - lat_min)) * nrows
        
        # Ensure pixel indices are integers
        return int(lat_pixel), int(lon_pixel)

    def locations2pixels(self, lat: np.ndarray, lon: np.ndarray):
        """
        Convert geographic coordinates to pixel coordinates on an image.
        
        Parameters:
        - lat np.ndarray: Latitude of the point.
        - lon np.ndarray: Longitude of the point.
        
        Returns:
        - tuple: (np.ndarray, np.ndarray) pixel coordinates.
        """
        lon_min, lon_max, lat_min, lat_max = self.extent
        nrows, ncols = self.image_shape[:2]
        
        # Normalize coordinates
        lon_pixel = ((lon - lon_min) / (lon_max - lon_min)) * ncols
        lat_pixel = ((lat_max - lat) / (lat_max - lat_min)) * nrows
        
        # Ensure pixel indices are integers
        print(f"Lon <: {(lon<lon_min).sum()}, Lon>: {(lon>lon_max).sum()}")
        print(f"Lat <: {(lat<lat_min).sum()}, Lat>: {(lat>lat_max).sum()}")
        return lat_pixel.astype(np.int32), lon_pixel.astype(np.int32)
    
    def get_charter_locations(self, charter_md5s: Union[List[str], None]) -> Tuple[np.ndarray, np.ndarray]:
        """
        Get the locations of the charters specified by their MD5 hashes.
        
        Parameters:
        - charter_md5s (List[str]): List of MD5 hashes of the charters.
        
        Returns:
        - List[Tuple[float, float]]: List of (latitude, longitude) tuples.
        """
        if charter_md5s is None:
            charter_md5s = list(self.charter_locations.keys())
        res = np.array([self.charter_locations[md5] for md5 in charter_md5s])
        return res[:, 0], res[:, 1]
    

    # def __call__(self, lat: Union[float, np.ndarray], lon: Union[float, np.ndarray]):
    #     if isinstance(lat, np.ndarray) and isinstance(lon, np.ndarray):
    #         return self.locations2pixels(lat, lon)
    #     elif isinstance(lat, float) and isinstance(lon, float):
    #         return self.location2pixels(lat, lon)
    #     else :
    #         raise ValueError("Invalid input types. Must be either float or np.ndarray.")

    # Function to render a map to a NumPy array
    def render_empty_map(self, edgecolor='black', facecolor='lightgray', lake_color='lightblue', river_color='blue'):
        fig = plt.figure(figsize=(10, 8)) # Todo: make this a data member
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.set_extent(self.extent, crs=ccrs.PlateCarree())
        
        # Add map features
        #ax.add_feature(cfeature.BORDERS, linestyle='-', edgecolor='black')
        ax.add_feature(cfeature.COASTLINE, edgecolor=edgecolor)
        ax.add_feature(cfeature.LAND, facecolor=facecolor)
        ax.add_feature(cfeature.LAKES, edgecolor=edgecolor, facecolor=lake_color)
        ax.add_feature(cfeature.RIVERS, edgecolor=river_color)

        # Render to an array
        fig.canvas.draw()
        map_image = np.array(fig.canvas.renderer.buffer_rgba())
        plt.close(fig)
        return map_image
    
    def render_points(self, pixels_long, pixels_lat, res_img: Union[np.ndarray, None] = None):
        if res_img is None:
            res_img = np.zeros(self.image_shape)
        else:
            print(f"Res image shape: {res_img} Image shape: {self.image_shape}")
            assert res_img.shape == self.image_shape, "Image shape mismatch"
        np.add.at(res_img, (pixels_long, pixels_lat), 1)
        res_img = res_img ** 0.5
        res_img /= res_img.max()
        return res_img


    def render_points_and_map(self, latitude, longitude, edgecolor='black', facecolor='lightgray', lake_color='lightblue', river_color='blue'):
        fig = plt.figure(figsize=(self.image_shape[1] / 100, self.image_shape[0] / 100), dpi=100)
        ax = plt.axes(projection=ccrs.PlateCarree())
        ax.set_extent(self.extent, crs=ccrs.PlateCarree())
        
        # Add map features
        ax.add_feature(cfeature.BORDERS, linestyle='-', edgecolor='black')
        ax.add_feature(cfeature.COASTLINE, edgecolor=edgecolor)
        ax.add_feature(cfeature.LAND, facecolor=facecolor)
        ax.add_feature(cfeature.LAKES, edgecolor=edgecolor, facecolor=lake_color)
        ax.add_feature(cfeature.RIVERS, edgecolor=river_color)
        longitude = longitude + np.random.normal(0, 0.1, len(longitude))
        latitude = latitude + np.random.normal(0, 0.1, len(latitude))
        ax.scatter(longitude, latitude, color='red', alpha=.01, s=5, zorder=5, transform=ccrs.PlateCarree())

        plt.subplots_adjust(left=0, right=1, top=1, bottom=0)
        ax.axis('off')

        # Render the map to a NumPy array
        fig.canvas.draw()        
        # Render to an array
        map_image = np.array(fig.canvas.renderer.buffer_rgba())
        plt.close(fig)
        return map_image



def get_charter_location_data(charter_paths: List[str], fsdb_root: str):
    location_dicts = load_location_data(fsdb_root)
    latitude = []
    longitude = []
    for location in location_dicts.values():
        latitude.append(location[0])
        longitude.append(location[1])
    return latitude, longitude


if __name__ == "__main__":
    p = {
        'fsdb_root': "./",
        'extent': "[-10.0, 40.0, 35.0, 70.0]",
        "map_width": 1000,
        "map_height": 800,
        "charter_glob": "*/*/*",
    }

    args, _ = fargv.fargv(p)
    renderer = MapRenderer(extent=eval(args.extent), image_shape=(args.map_height, args.map_width), fsdb_root=args.fsdb_root, charter_glob=args.charter_glob)

    # Convert extent argument to list
    
    #map_image = renderer.render_empty_map()
    latitudes, longtitudes  = renderer.get_charter_locations(None)
    #print(f"Latitudes: {latitudes[:10]}")
    #print(f"Longtitudes: {longtitudes[:10]}")
    #latitudes = np.array([48.8566, 52.5200, 41.9028])  # Paris, Berlin, Rome
    #longtitudes = np.array([2.3522, 13.4050, 12.4964])
    latitude_pixels, longtitude_pixels  = renderer.locations2pixels(latitudes, longtitudes)
    points_image = renderer.render_points_and_map(latitudes, longtitudes)

    # Optional: Display the images for verification
    plt.figure(figsize=(10, 8))
    #plt.title(f"{len(latitudes)} charters")
    plt.imshow(points_image)
    ax = plt.gca()    
    plt.axis("off")
    plt.show()

    #plt.figure(figsize=(10, 8))
    #plt.title("Points Image")
    #plt.imshow(points_image)
    #plt.axis("off")
    #plt.show()

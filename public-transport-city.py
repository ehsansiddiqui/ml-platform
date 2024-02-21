#!/usr/bin/env python
# coding: utf-8

# # Requirement:

# External library to import

# In[1]:


import sys

sys.path.insert(0, './library/')
import zipfile
import os
import time
import pymongo as pym
import pandas as pd
import folium
import numpy as np
import requests
import numba
from shapely.geometry import Polygon, LineString, shape, mapping, Point
import math
import geopy
from shapely.geometry import Polygon, MultiPolygon, Point, mapping
from geopy.distance import geodesic, great_circle
from folium.plugins import FastMarkerCluster
from datetime import datetime
from geopy.distance import geodesic, great_circle

# # Data:
# 
# 1. gtfs file of the city. 
#  ->[repository of gtfs file https://transitfeeds.com/]
# 2. pbf file of [openstreetmap](openstreetmap.org) extract from of the city/region of interest. ->[repository of osm extract: http://download.geofabrik.de/]

# # Url and paths  [**set it!**]
# ### mongodb settings

# In[2]:


city = 'Budapest'  # name of the city
urlMongoDb = "mongodb://localhost:27017/";  # url of the mongodb database

client = pym.MongoClient(urlMongoDb)
gtfsDB = client['PublicTransportAnalysis']

# OPTIONAL
urlMongoDbPop = "mongodb://localhost:27017/";  # url of the mongodb database of population data
popDbName = 'PublicTransportAnalysis'  # "population"
popCollectionName = "POP"  # "europe"
popField = "TOT_P_2018"  # "pop"

# ### path of the gtfs files.

# In[3]:


directoryGTFS = './gtfs/' + city + '/'  # directory of the gtfs files.

# ### Settings of the date and the day for the computation of accessibility quantitites
# the date must be in the interval of validity of the gtfs files, check it in the "calendar.txt" and "calendar_dates.txt" files inside the gtfs zip files.

# In[4]:


from libConnections import printGtfsDate

printGtfsDate(directoryGTFS)

# In[5]:


day = "20170607"  # hhhhmmdd
dayName = "wednesday"  # name of the corresponding day

#  ## Define url of the osrm server

# In[6]:


urlServerOsrm = 'http://localhost:5000/';  # url of the osrm server of the city

# ## Parameters thst define the resolution and extention of tesselletion and the maximum of the walking time

# In[7]:


# grid step of the hexagonal tesselletion in kilometers
gridEdge = 1

# parameters of walking distance
timeWalk = 15 * 60  # seconds
velocityWalk = 1.39  # m/s ***5km/h***
distanceS = timeWalk * velocityWalk

# # Start of the computation

# ### Read stops, routes, trips, calendar and calendar_dates from gtfs

# ### add population data

# In[8]:

from pathlib import Path
import geopandas as gpd
import geojson

shapefile = gpd.read_file(Path("Pop/Budapest/Budapest.shp"))
shapefile.to_file(Path('Pop/Budapest/myshpfile.geojson'), driver='GeoJSON')
with open(Path("Pop/Budapest/myshpfile.geojson")) as f:
    gj = geojson.load(f)
features = gj['features']
gtfsDB["POP"].drop()
gtfsDB["POP"].insert_many(features)

# In[9]:


from libStopsPoints import loadGtfsFile

listOfFile = ['stops.txt', 'routes.txt', 'trips.txt', 'calendar.txt', 'calendar_dates.txt',
              'stop_times.txt']  # , 'stop_times.txt']#, 'shapes.txt']
loadGtfsFile(gtfsDB, directoryGTFS, city, listOfFile)

# ## Fill the database with the connections

# In[10]:


from libConnections import readConnections

readConnections(gtfsDB, city, directoryGTFS, day, dayName)

# ## remove stops with no connections
# #### and add to each stop the pos field

# In[12]:


from libStopsPoints import removingStopsNoConnections, setPosField, removeStopsOutBorder

# removeStopsOutBorder(gtfsDB, city, 'OECD_city', ["commuting_zone", "city_core"])
removingStopsNoConnections(gtfsDB, city)
setPosField(gtfsDB, city)

# In[13]:


from libConnections import updateConnectionsStopName

updateConnectionsStopName(gtfsDB, city)

# # Tassel with exagons

# ### List of all stops

# In[14]:


from libStopsPoints import returnStopsList

stopsList = returnStopsList(gtfsDB, city)

# ## Compute the box that include all stops
# The edge of such box are enlarged by distanceS.

# In[15]:


from libStopsPoints import boundingBoxStops, mapStops
from IPython.core.display import display, HTML

display(HTML('<h1>All stops of the public transport present in the gtfs files</h1>'))
bbox = boundingBoxStops(stopsList)
mapStops(bbox, stopsList)

# ## Tassel the box with exagons.

# In[19]:


from libHex import hexagonalGrid

hexBin, pointBin = hexagonalGrid(bbox, gridEdge, gtfsDB['stops'], distanceS, city)

# In[20]:


from libHex import insertPoints

insertPoints(pointBin, city, gtfsDB)
print('total number of hexagons created : {0}'.format(gtfsDB['points'].find({'city': city}).count()))

# In[21]:


from libHex import unionHexs
from IPython.core.display import display, HTML

display(HTML('<h1>First tesselletion of the area served by public transport</h1>'))
latlon = list(reversed(gtfsDB['points'].find_one({'city': city})['point']['coordinates']))
map_osm = folium.Map(location=latlon, zoom_start=9);
map_osm.choropleth(unionHexs(pointBin), fill_color='#3288bd', fill_opacity=0.3, line_color='#3288bd', line_weight=2,
                   line_opacity=1)
map_osm

# ## Find the hex with walkingTime less than timeWalk from a stops

# In[22]:


from libHex import pointsServed

pointsServed(gtfsDB, stopsList, urlServerOsrm, distanceS, timeWalk, city)

# In[26]:


print("Number of hexagons: {0}".format(gtfsDB['points'].find({'served': True, 'city': city}).count()))

# ## Setting field "pos" for points for performance

# In[27]:


from libHex import settingHexsPos

settingHexsPos(gtfsDB, city)

# In[28]:


from libHex import showHexs
from IPython.core.display import display, HTML

display(HTML('<h1>Tesselletion of the area served by the public transport</h1>'))
showHexs(gtfsDB, city, 10)

# ## Setting Population of Hexagons

# In[29]:


from libHex import setHexsPop

if urlMongoDbPop != "" and popCollectionName != "":
    clientPop = pym.MongoClient(urlMongoDbPop)
    popDb = clientPop[popDbName]
    popCollection = popDb[popCollectionName]
    setHexsPop(gtfsDB, popCollection, popField, city)
else:
    print("Population NOT INSERTED!")

res = gtfsDB['points'].update_many({'pop': {'$exists': False}}, {'$set': {'pop': 0}})
print("n° of matched hexagons with population Polygons: {0} \n not matched: {1} (setted to zero)".format(
    gtfsDB['points'].find({'pop': {'$exists': True}}).count(),
    res.modified_count))

# # Adding the walking time between stops and points

# In[30]:


from libStopsPoints import computeNeigh

computeNeigh(gtfsDB, urlServerOsrm, distanceS, timeWalk, city)

# # Compute quantities and observable

# TimeList is the list of starting time for computing the isochrones

# In[35]:


timeList = list(range(6, 22, 2))  # [7,10,13,16,19,22] # List of starting time for computing the isochrones
# timeList = [7,10,13,16,19,22] # List of starting time for computing the isochrones
hStart = timeList[0] * 3600

# ### List of connections

# In[36]:


from libConnections import makeArrayConnections

arrayCC = makeArrayConnections(gtfsDB, hStart, city)

# ### List of list of the points and stops neighbors

# In[37]:


from libStopsPoints import listPointsStopsN

arraySP = listPointsStopsN(gtfsDB, city)

# ## Compute accessibility quantities

# In[38]:
import warnings
warnings.filterwarnings('ignore')

import imp
import icsa
import libAccessibility

imp.reload(libAccessibility)
from icsa import computeAccessibilities

imp.reload(icsa)
listAccessibility = ['velocityScore', 'socialityScore', 'velocityScoreGall',
                     'socialityScoreGall', 'velocityScore1h', 'socialityScore1h',
                     'timeVelocity', 'timeSociality']

computeIsochrone = False
if 'isochrones' in gtfsDB.collection_names():
    # gtfsDB['isochrones'].delete_many({'city':city})
    pass
for timeStart in timeList:
    timeStart *= 3600
    print('Time Isochrone Start: {0}'.format(timeStart / 3600, ))
    computeAccessibilities(city, timeStart, arrayCC, arraySP, gtfsDB, computeIsochrone, timeStart / 3600 == timeList[0],
                           listAccessibility=listAccessibility)

# ## Compute averages of the accessiblity quantities computed

# In[40]:


from libStopsPoints import computeAverage

computeAverage(listAccessibility, gtfsDB, city)

# # RESULTS

# ## maps

# In[41]:


from libHex import reduceGeojsonInShellSubField
from IPython.core.display import display, HTML

field1 = 'velocityScore'
field2 = 'avg'
color = ['#993404', "#f16913", "#fdae6b", '#74c476', '#31a354', '#006d2c', "#6baed6", "#4292c6", "#2171b5", '#08519c',
         '#f768a1', '#dd3497', '#ae017e', '#49006a'];
shell = [0., 2., 4., 5, 6., 7, 8., 9, 10., 11, 12., 13, 15, 17.];
print("number of hexs in total", gtfsDB['points'].find({field1: {'$exists': True}, 'city': city}).count())
res = reduceGeojsonInShellSubField(list(gtfsDB['points'].find({'city': city})), field1, field2, color, shell)
# res = showMapHexRedux(city, gtfsDB['points'], field = field, shell = shell, save=True)

display(HTML('<h1>Velocity Score</h1>'))

res[1]

# In[42]:


from libHex import reduceGeojsonInShellSubField
from IPython.core.display import display, HTML

field1 = 'socialityScore'
field2 = 'avg'
color = ["#000000", "rgb(95, 95, 95)", "rgb(180, 180, 180)", "rgb(8, 48, 107)", "rgb(15, 87, 159)", "rgb(47, 126, 188)",
         "rgb(109, 174, 213)", "rgb(181, 212, 233)", "rgb(253, 202, 148)",
         "rgb(253, 176, 122)", "rgb(250, 142, 93)", "rgb(241, 108, 73)", "rgb(224, 69, 48)", "rgb(243, 105, 163)",
         "rgb(224, 62, 152)", "rgb(153, 3, 124)", "rgb(73, 0, 106)"]
shell = [0, 50000, 100000, 200000, 300000, 400000, 500000, 600000, 700000, 800000, 900000, 1000000, 1500000, 2000000,
         2500000, 3000000];
print("number of hexs in total", gtfsDB['points'].find({field1: {'$exists': True}, 'city': city}).count())
res = reduceGeojsonInShellSubField(list(gtfsDB['points'].find({'city': city})), field1, field2, color, shell)
# res = showMapHexRedux(city, gtfsDB['points'], field = field, shell = shell, save=True)

display(HTML('<h1>Sociality Score</h1>'))

res[1]

# # Saving File
# Make ZIP file containig all the public transports information needed in order to add the city to the [citychrone](www.citychrone.org) platform.

# In[39]:


import saveData

newScenario = True  # If True in the citychrone platform tensting new scenario on the city is allowed.
from saveData import makeZipCitychrone

if 'arrayCC' in locals():
    makeZipCitychrone(city, gtfsDB, arrayCC, newScenario=newScenario, urlServerOsrm=urlServerOsrm)
else:
    makeZipCitychrone(city, gtfsDB, newScenario=True)

# # [Optional]
# # Analisys on the accessibility quantities.
# 
# ## Compute average time distance from the center
# Computing the average time distance from the center of the city. 
# We consider two center: 
# 1. where the velocityScore is max
# 2. Where the socialityScore is max.

# In[ ]:


gtfsDB['points'].find_one({'city': city})["velocityScore"].keys()
timeListSec = []
for k in gtfsDB['points'].find_one({'city': city})["velocityScore"].keys():
    try:
        timeListSec.append(int(k))
    except:
        pass
if len(timeListSec) > 10:
    timeListSec = timeListSec[2:]
print(timeListSec)

# In[ ]:


from libConnections import makeArrayConnections
from libStopsPoints import listPointsStopsN
from libHex import reduceGeojsonInShell
from icsa import coumputeAvgTimeDistance

startPoint = gtfsDB['points'].find({'city': city}, sort=[('velocityScore.avg', -1)])[0]

if 'arrayCC' not in locals():
    arrayCC = makeArrayConnections(gtfsDB, 0, city)
if 'arraySP' not in locals():
    arraySP = listPointsStopsN(gtfsDB, city)

timeDist = coumputeAvgTimeDistance(startPoint, timeListSec, arrayCC, arraySP, gtfsDB, city)
startPointLatLon = [startPoint['point']["coordinates"][1], startPoint['point']["coordinates"][0]]
for pos, tDist in enumerate(timeDist):
    pointSelectedLonLat = gtfsDB["points"].find_one({'pos': pos, "city": city})["point"]["coordinates"]
    sVelDist = geodesic(startPointLatLon, (pointSelectedLonLat[1], pointSelectedLonLat[0])).meters  # dist in meter
    gtfsDB["points"].update_one({'pos': pos, 'city': city}, {'$set': {'tVelDist': tDist, "sVelDist": sVelDist}})
print(timeDist)
pointsList = list(gtfsDB['points'].find({'city': city}, {'pointN': 0, 'stopN': 0}))
res = reduceGeojsonInShell(pointsList, 'tVelDist')
res[1]

# In[ ]:


startPoint = gtfsDB['points'].find({'city': city}, sort=[('socialityScore.avg', -1)])[0]

if 'arrayCC' not in locals():
    arrayCC = makeArrayConnections(gtfsDB, 0, city)
if 'arraySP' not in locals():
    arraySP = listPointsStopsN(gtfsDB, city)

timeDist = coumputeAvgTimeDistance(startPoint, timeListSec, arrayCC, arraySP, gtfsDB, city)
for pos, tDist in enumerate(timeDist):
    gtfsDB["points"].update_one({'pos': pos, 'city': city}, {'$set': {'tSocDist': tDist}})
timeDist
pointsList = list(gtfsDB['points'].find({'city': city}, {'pointN': 0, 'stopN': 0}))
res = reduceGeojsonInShell(pointsList, 'tSocDist')
res[1]


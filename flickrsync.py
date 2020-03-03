#!/usr/bin/python3

# MIT License
#
# Copyright (c) 2018 Graham White
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

# Some useful info/links...
# http://www.exiv2.org/tags.html
# https://www.flickr.com/services/api/
# https://stuvel.eu/flickrapi-doc/
# http://effbot.org/zone/element.htm
# http://effbot.org/zone/element-xpath.htm

import os
import sys
from dotenv import load_dotenv
from pathlib import Path
import urllib.request
import pyexiv2
from pyexiv2.utils import make_fraction
import flickrapi
import webbrowser
import datetime


def setExif(filename, exif):
    """Writes exif data to a file.

    Exif updates are additive i.e existing exif data in an image is not
    overwritten by the exif data specified, only blanks are filled in

    Keyword arguments:
    filename -- the file path and name string of the file to write to
    exif -- a dictionary of Exif-Tag-Name=Value entries
    """

    # read the original exif from the file
    metadata = pyexiv2.ImageMetadata(filename)
    metadata.read()

    writeRequired = False

    # merge the provided exif with the original exif (original exif has priority)
    for exifTag in exif:
        if exifTag not in metadata.exif_keys:
            metadata[exifTag] = exif[exifTag]
            writeRequired = True

    # write the merged exif if necessary
    if writeRequired:
        metadata.write()


def flickrAuth():
    """Authenticates to the Flickr API."""

    # Only do this if we don't have a valid token already
    if not flickr.token_valid(perms='read'):

        # Get a request token
        flickr.get_request_token(oauth_callback='oob')

        # Open a browser at the authentication URL. Do this however
        # you want, as long as the user visits that URL.
        authorize_url = flickr.auth_url(perms='read')
        webbrowser.open_new_tab(authorize_url)

        # Get the verifier code from the user. Do this however you
        # want, as long as the user gives the application the code.
        verifier = input('Verifier code: ')

        # Trade the request token for an access token
        flickr.get_access_token(verifier)


def flickrGetPhotoSets(incNotInSet=False):
    """Returns an array of photosets.

    Keyword arguments:
    incNotInSet -- whether to include an entry for photos not in a set (default=False)
    """
    if incNotInSet:
        photosets = [{'title': 'Photos not in an album', 'id': None, 'total': None}]
    else:
        photosets = []

    for photoset in flickr.photosets.getList().getiterator('photoset'):
        title = photoset.find('title').text
        id = photoset.get('id')
        total = int(photoset.get('photos')) + int(photoset.get('videos'))
        photosets.append({'title': title, 'id': id, 'total': total})
    return photosets


def getLicense(photoInfo):
    """Returns a license string for a photo.

    Keyword arguments:
    photoInfo -- the photo info as return by the Flickr getInfo API call
    """

    licenses = [
        "All Rights Reserved"
        "CC BY-NC-SA (Attribution-NonCommercial-ShareAlike) License",
        "CC BY-NC (Attribution-NonCommercial) License",
        "CC BY-NC-ND (Attribution-NonCommercial-NoDerivs) License",
        "CC BY (Attribution) License",
        "CC BY-SA (Attribution-ShareAlike) License",
        "CC BY-ND (Attribution-NoDerivs) License",
        "No known copyright restrictions",
        "United States Government Work",
        "Public Domain Dedication (CC0)",
        "Public Domain Mark"
    ]
    return licenses[int(photoInfo.get('license'))]


def getOwner(photoInfo):
    """Returns the owner name string for a photo.

    Keyword arguments:
    photoInfo -- the photo info as return by the Flickr getInfo API call
    """

    return photoInfo.find('owner').get('realname')


def getCopyright(photoInfo):
    """Returns a copyright string for a photo.

    Keyword arguments:
    photoInfo -- the photo info as return by the Flickr getInfo API call
    """

    taken = photoInfo.find('dates').get('taken')
    year = taken[:4]
    owner = getOwner(photoInfo)
    license = getLicense(photoInfo)

    copyright = "Copyright, " + owner + ", " + year + ". " + license
    return copyright


def generateFilename(photoInfo, photoNum):
    """Creates a file system file name for a photo.

    The file name will be in the format date-taken_title.extension.  For
    example, 20180521203625_My_Flickr_Picture.jpg.  The date taken will be a
    numeric string which means the pictures on the file system will sort in date
    order when listed; folloed by underscore; followed by the title of the image
    with spaces replaced with underscores; followed by the image extension.  All
    video files receive the mp4 extension, images will have their original type
    and extension preserved.

    Keyword arguments:
    photoInfo -- the photo info as return by the Flickr getInfo API call
    """

    # get the date the photo was taken
    taken = photoInfo.find('dates').get('taken')
    # compress the string a bit and remove the space
    taken = taken.replace("-", "").replace(":", "").replace(" ", "-")

    try:
        # get the title and replace spaces with underscore
        title = photoInfo.find('title').text.replace(" ", "_")
    except:
        title = 'Unknown'

    # get the file extension
    if photoInfo.get('media') == 'video':
        extension = 'mp4'
    else:
        extension = photoInfo.get('originalformat')

    # build and return the filename string
    if photoNum is None:
        return taken + "_" + title + "." + extension
    else:
        return photoNum + "_" + taken + "_" + title + "." + extension


def gpsDecimalToDMS(decimal, loc):
    """Returns a GPS coordinate in DMS format.

    Keyword arguments:
    decimal -- a real number containing the lat or lon
    loc -- an array of strings representing lat or lon
        -- must be one of ["S", "N"] or ["W", "E"]
    """
    if decimal < 0:
        latlonRef = loc[0]
    elif decimal > 0:
        latlonRef = loc[1]
    else:
        latlonRef = ""
    abs_value = abs(decimal)
    deg = int(abs_value)
    t = (abs_value-deg)*60
    min = int(t)
    sec = round((t - min) * 60, 6)
    return (deg, min, sec, latlonRef)


def gpsDecimalLatToDMS(decimalLat):
    """Returns a GPS coordinate in DMS format.

    Wrapper function to convert latitude from decimal to DMS format.

    Keyword arguments:
    decimalLat -- a real number containing the latitude
    """

    return gpsDecimalToDMS(decimalLat, ["S", "N"])


def gpsDecimalLonToDMS(decimalLon):
    """Returns a GPS coordinate in DMS format.

    Wrapper function to convert longitude from decimal to DMS format.

    Keyword arguments:
    decimalLon -- a real number containing the longitude
    """

    return gpsDecimalToDMS(decimalLon, ["W", "E"])


def downloadPhoto(path, photoId, photoNum=None):
    """Downloads an image and sets exif data.

    Keyword arguments:
    path -- a string containing the name of the directory to write to
    photoId -- a string containing the ID number of the image to download
    """

    # create the directory to store the images
    setPath = path.replace("/", "-")
    if not os.path.exists(setPath):
        os.makedirs(setPath)

    # download the photo metadata
    photoInfo = flickr.photos.getInfo(photo_id=photoId).find('photo')

    # work out a filename for the photo once downloaded
    filename = path + os.sep + generateFilename(photoInfo, photoNum)

    # try downloading the file
    try:
        sizes = flickr.photos.getSizes(photo_id=photoId).find('sizes')
        if filename.endswith('.mp4'):
            url = sizes.find('.//size[@label="Video Original"]').get('source')
        else:
            url = sizes.find('.//size[@label="Original"]').get('source')
        urllib.request.urlretrieve(url, filename)
        print(filename)
    except:
        return

    # a place to build up the exif info to write
    photoExif = {}

    if not filename.endswith('.mp4'):
        # work out the exif and XMP vales
        photoExif['Exif.Image.Copyright'] = getCopyright(photoInfo)
        photoExif['Exif.Image.Artist'] = getOwner(photoInfo)
        photoExif['Xmp.dc.rights'] = photoExif['Exif.Image.Copyright']
        photoExif['Xmp.dc.creator'] = [getOwner(photoInfo)]
        photoExif['Xmp.xmpRights.Owner'] = photoExif['Xmp.dc.creator']
        photoExif['Xmp.xmpRights.Marked'] = True
        photoExif['Xmp.xmpRights.UsageTerms'] = getLicense(photoInfo)
        photoExif['Xmp.dc.title'] = photoInfo.find('title').text or 'Unknown'
        photoExif['Exif.Image.ImageDescription'] = photoExif['Xmp.dc.title']

        # only set the description if there's one to set (or default to setting the same as the title)
        description = photoInfo.find('description').text
        if description is None:
            description = photoExif['Xmp.dc.title']
        photoExif['Xmp.dc.description'] = description
        photoExif['Exif.Photo.UserComment'] = description

        # set the subject using the image tags (if there are any)
        tags = []
        for tag in photoInfo.find('tags').getiterator('tag'):
            tags.append(tag.text)
        if len(tags) > 0:
            photoExif['Xmp.dc.subject'] = tags

        # set the date taken
        taken = photoInfo.find('dates').get('taken')
        takenFormatted = datetime.datetime.strptime(taken, '%Y-%m-%d %H:%M:%S')
        photoExif['Xmp.dc.date'] = [takenFormatted]
        photoExif['Xmp.xmp.CreateDate'] = takenFormatted

        # add GPS coordinates if available
        location = photoInfo.find('location')
        if location is not None:
            lat = gpsDecimalLatToDMS(float(location.get('latitude')))
            lon = gpsDecimalLonToDMS(float(location.get('longitude')))
            latDMS = (make_fraction(lat[0], 1), make_fraction(int(lat[1]), 1), make_fraction(int(lat[2]*1000000), 1000000))
            lonDMS = (make_fraction(lon[0], 1), make_fraction(int(lon[1]), 1), make_fraction(int(lon[2]*1000000), 1000000))
            photoExif["Exif.GPSInfo.GPSVersionID"] = '2 0 0 0'
            photoExif["Exif.GPSInfo.GPSLatitude"] = latDMS
            photoExif["Exif.GPSInfo.GPSLatitudeRef"] = lat[3]
            photoExif["Exif.GPSInfo.GPSLongitude"] = lonDMS
            photoExif["Exif.GPSInfo.GPSLongitudeRef"] = lon[3]
            photoExif["Exif.GPSInfo.GPSDateStamp"] = datetime.datetime.strptime(taken, '%Y-%m-%d %H:%M:%S').strftime('%Y:%m:%d')

        setExif(filename, photoExif)


def downloadPhotoSet(setName, setID, total):
    """Downloads images from a photoset and sets their exif data.

    Keyword arguments:
    setName -- a string containing the name of the set to download
    setID -- a string containing the ID number of the set to download
    total -- an integer containing the total number of items in the set
    """

    for i, photo in enumerate(flickr.walk_set(setID)):

        # format the number of the photo in the set
        j = i + 1
        if total < 10:
            photoNum = str(j)
        elif total < 100:
            photoNum = f'{j:02}'
        elif total < 1000:
            photoNum = f'{j:03}'
        else:
            photoNum = f'{j:04}'

        photoId = photo.get('id')
        downloadPhoto(setName, photoId, photoNum)


def downloadNotInSet(setPath):
    """Downloads all images that are not part of a set.

    Keyword arguments:
    setPath -- the name of the directory in which the images will be saved
    """

    getNextPage = True
    page = 1

    while getNextPage:
        photos = flickr.photos.getNotInSet(page=page, per_page=500).findall('.//photo')

        for photo in photos:
            photoId = photo.get('id')
            downloadPhoto(setPath, photoId)

        if len(photos) == 100:
            page = page + 1
        else:
            getNextPage = False


def rangeSplit(rangeStr):
    """Return an array of numbers from a specified set of ranges.

    Given a string such as "1 2 4-6 8" will return [1,2,4,5,6,8].  The numbers
    and ranges can either be space separated or comma separated (but not both).

    Keyword arguments:
    rangeStr -- a string containing ranges such as "1 2 4-6 8"
    """

    result = []
    splitChar = ' '
    if ',' in rangeStr:
        splitChar = ','

    for part in rangeStr.split(splitChar):
        if '-' in part:
            a, b = part.split('-')
            a, b = int(a), int(b)
            result.extend(range(a, b + 1))
        else:
            a = int(part)
            result.append(a)
    return result


if __name__ == "__main__":
    # load required env vars
    env_path = Path('.') / '.env'
    load_dotenv(dotenv_path=env_path, verbose=True)
    api_key = os.getenv("FLICKRSYNC_APIKEY")
    api_secret = os.getenv("FLICKRSYNC_APISECRET")

    # bomb out if we don't have the required env vars
    if api_key is None or api_secret is None:
        print("You must specify your API key and secret in your environment")
        sys.exit(1)

    # set up the Flickr API
    flickr = flickrapi.FlickrAPI(api_key, api_secret)
    flickrAuth()

    # download a list of photosets and add an entry for photos not in a set
    photosets = flickrGetPhotoSets(incNotInSet=True)

    # print out a list of sets from the authorised user
    for setNumber in range(0, len(photosets)):
        columnWidth = '{:' + str(len(str(len(photosets)))) + '}'
        print(columnWidth.format(setNumber) + ") " + photosets[setNumber]['title'])

    # ask which sets to download (supports comma or space separation and ranges)
    setsToDownload = input('Which albums do you want to download: ')
    setsToDownload = rangeSplit(setsToDownload)

    # download the specified sets
    for setToDownload in setsToDownload:
        if photosets[setToDownload]['id'] is not None:
            downloadPhotoSet(photosets[setToDownload]['title'],
                             photosets[setToDownload]['id'],
                             photosets[setToDownload]['total'])
        else:
            downloadNotInSet(photosets[setToDownload]['title'])

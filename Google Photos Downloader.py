from __future__ import print_function
import pickle
import time
import subprocess
import json
import sys
import os
import requests
import piexif
import pytz
from PIL import Image
from datetime import datetime
from alive_progress import alive_bar
from dotenv import load_dotenv 
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

#TO DO:
#-Deal with case where items exceed pageSize when getting photos. Idea is to ask user for date where they wish to pull photos from. 
# *Can replicate the generator function for the album code.
# *Eliminates the need for the last updated index file.
# *Might speed things up in the album loading if we just yield until the date is passed.

load_dotenv()

#Generator that yields a photo from an album.
def get_photos(service, album_id, page_size):
    params = {'albumId':album_id, 'pageSize':page_size}

    while True:
        request = service.mediaItems().search(**params)
        response = request.execute()

        for content in response['mediaItems']:
            yield content
        
        params['pageToken'] = response.get('nextPageToken')

        if response.get('nextPageToken') is None:
            break

#Converts UTC date to PT date with specific date format. Accounts for daylight savings
def utc_to_pt(utc_string,format="%Y:%m:%d %H:%M:%S"):
    utc_timezone = pytz.timezone("UTC")
    date = utc_timezone.localize(datetime.strptime(utc_string, "%Y-%m-%dT%H:%M:%SZ"))

    pt_timezone = pytz.timezone("US/Pacific")

    #Convert UTC to PT
    pt_date = date.astimezone(pt_timezone)

    return pt_date.strftime(format)

#AUTH Code Found Here: https://stackoverflow.com/questions/58928685/google-photos-api-python-working-non-deprecated-example

credentialsFile = 'credentials.json' 
pickleFile = 'token.pickle' 

SCOPES = ['https://www.googleapis.com/auth/photoslibrary']
creds = None
if os.path.exists(pickleFile):
    with open(pickleFile, 'rb') as token:
        creds = pickle.load(token)
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            credentialsFile, SCOPES)
        creds = flow.run_local_server()
    with open(pickleFile, 'wb') as token:
        pickle.dump(creds, token)

service = build('photoslibrary', 'v1', credentials=creds, static_discovery=False)
request = service.mediaItems().list(pageSize=30) #Must modify this using nextpage token
response = request.execute()

photos = response['mediaItems']

last_updated_index = None
last_updated_id = None

with open('newest_id_file.txt') as f:
    last_updated_id = f.read()

#Find the index of the last updated photo. The first element in photos is the most recent photo
for index, dic in enumerate(photos):
    if dic['id'] == last_updated_id:
        last_updated_index = index
        break
    else:
        last_updated_index = -1

# print(last_updated_index) #DEBUG LINE
if(last_updated_index == 0):
    print("No new photos have been uploaded. Script exited.")
    sys.exit()

# Experimental code for updating based on a date instead of relying on a set thing.
# last_updated_index = next((index for (index, d) in enumerate(reversed(photos)) if "2022-09-03" in d['mediaMetadata']['creationTime']), None)
# print(len(photos) - last_updated_index -1)

photos = photos[:last_updated_index+1]

#Patch for albumId not being a valid arg: https://github.com/googleapis/google-api-python-client/issues/733
search_params = {
  "albumId": {
    "description": "Identifier of an album. If populated, lists all media items in specified album. Can't set in conjunction with any filters.",
    "location": "query",
    "type": "string"
  },
  "pageSize": {
    "description": "Maximum number of media items to return in the response. Fewer media items might be returned than the specified number. The default pageSize is 25, the maximum is 100.",
    "location": "query",
    "type": "integer",
    "format": "int32"
  },
  "pageToken": {
    "description": "A continuation token to get the next page of the results. Adding this to the request returns the rows after the pageToken. The pageToken should be the value returned in the nextPageToken parameter in the response to the searchMediaItems request.",
    "location": "query",
    "type": "string"
  },
  "filters": {
    "description": "Filters to apply to the request. Can't be set in conjunction with an albumId.",
    "location": "query",
    "type": "object"
  }
}

request = service.albums().list(pageSize=30) #Only need 30 items since there are only 28 albums currently. Might change this later to reflect pageToken stuff.
response = request.execute()

albums = response['albums']

service._resourceDesc['resources']['mediaItems']['methods']['search']['parameters'].update(search_params)

albums_of_new_photos = []

album_media = []

# album_size_dict_old = {}

# if(os.path.exists('albums_sizes.json')):
#     with open('albums_sizes.json', 'r') as f:
#         album_size_dict_old = json.load(f)
# else:
#     for i in range(len(albums)):
#         album_size_dict_old[albums[i]['id']] = albums[i]['mediaItemsCount']
#     with open('albums_sizes.json', 'w') as f:
#         json.dump(album_size_dict_old,f)

# album_size_dict_new = {}

# for i in range(len(albums)):
#     album_size_dict_new[albums[i]['id']] = albums[i]['mediaItemsCount']

# set1 = set(album_size_dict_old.items())
# set2 = set(album_size_dict_new.items())

# print((set1 ^ set2) -set2) 

#Get a list of photos from each album and put them in a list.
with alive_bar(len(albums), dual_line=True, title='Albums',calibrate=10) as bar:

    for i in range(len(albums)):
        bar.text = '-> Loading album content, please wait...'

        album_content = [content for content in get_photos(service, albums[i]['id'],20)]
    
        album_media.append(album_content)
        bar()
 
album_titles = [] #List of album titles that a certain photo belongs to.

#Iterate through all albums and check which ones a photo belongs to.
for i in range(last_updated_index+2): # Iterate through each photo.

    #Add the list of album titles that a photo is in to the total list of albums with each index being the index of the photo.
    if(album_titles and i > 0):
        albums_of_new_photos.append(album_titles)
    elif (i > 0): #Without this the entire list would be shifted
        albums_of_new_photos.append(["Not in any album"])
    else:
        pass

    album_titles = [] #Reset after each iteration

    #Required since the last iteration will be skipped (hence the last_updated_index+2 in the above).
    if(i == last_updated_index+1):
        break

    for j in range(len(albums)): # Iterate through each album
        
        #Find out if photo is in the album
        for dic in album_media[j]:
            if dic['id'] == photos[i]['id']:
                album_titles.append(albums[j]['title'])
                break
            else:
                pass

        #Takes care of special cases where we can just end the iteration
        if(album_titles.count('Random People') or album_titles.count('Unspecified')):
            break
        elif(album_titles.count('Videos') or len(album_titles) >= 3):
            album_titles = ['Videos']
            break

#Takes care of duo photos here instead of the loop due to ordering issues
# print(albums_of_new_photos) #DEBUG LINE
albums_of_new_photos  = ["Group Stuff" if len(l) == 2 else l[0] for l in albums_of_new_photos]

list_no_exif = []
list_no_album = []

#Download all photos/videos and change the dates/titles for them to match up
with alive_bar(last_updated_index+1,  dual_line=True, title='Photos', calibrate=10) as bar:
    for i in range(last_updated_index+1):
        bar.text = "-> Downloading photos, please wait..."
        request = service.mediaItems().get(mediaItemId=photos[i]['id'])
        response = request.execute()

        #The '=dv' and '=d' download the videos and photos respectively in full quality and properly
        if (albums_of_new_photos[i] == "Videos"):
            media_url = response['baseUrl'] + '=dv'
        else:
            media_url = response['baseUrl'] + '=d'

        response = requests.get(media_url)
        photo = response.content

        is_video = False
        no_exif = False
        no_album = False
        filename = photos[i]['filename']
        file_dir = os.getenv('PHOTO_DIRECTORY')
        folder_name = albums_of_new_photos[i]
        creation_time = photos[i]['mediaMetadata']['creationTime']
        actual_date = utc_to_pt(creation_time)

        if (folder_name == "Not in any album"):
            list_no_album.append(filename)
            folder_name = 'Not Organized'

        with open(file_dir + folder_name + '\\' + filename, 'wb') as f:
            f.write(photo)

            if (folder_name == "Videos"):
                is_video = True
                pass
            else:
                im = Image.open(file_dir + folder_name + '\\' + filename)

                try:
                    exif_dict = im.info['exif']
                except KeyError:  # Some photos may not have EXIF data
                    list_no_exif.append((filename, actual_date))
                    no_exif = True
                else:
                    # Apply correct date from metadata
                    exif_dict = piexif.load(exif_dict)
                    piexif.remove(file_dir + folder_name + '\\' + filename)
                    encoded_date = actual_date.encode('utf-8')
                    exif_dict['Exif'][piexif.ExifIFD.DateTimeOriginal] = encoded_date
                    exif_dict['Exif'][piexif.ExifIFD.DateTimeDigitized] = encoded_date

                    # Apply changes to photos
                    exif_bytes = piexif.dump(exif_dict)
                    piexif.insert(exif_bytes, file_dir + folder_name + '\\' + filename)

        if (no_exif):
            exif_dict = {
                "0th": {},
                "Exif": {
                    piexif.ExifIFD.DateTimeOriginal: actual_date,
                    piexif.ExifIFD.DateTimeDigitized: actual_date
                },
                "GPS": {},
                "Interop": {},
                "1st": {},
                "thumbnail": None
            }
            exif_bytes = piexif.dump(exif_dict)
            im.save(file_dir + folder_name + '\\' +filename, exif=exif_bytes)
            im.close()
            #Only way to properly change the PNG time which is used by Windows instead of the new EXIF for some reason.
            if(filename.find("PNG")):
                subprocess.run(["exiftool", "-overwrite_original", f"-PNG:CreationTime={actual_date}", file_dir + folder_name + '\\' + filename],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # The following uses replace instead of rename since replace accounts for already existing files
        im.close()
        actual_date = datetime.strptime(actual_date,"%Y:%m:%d %H:%M:%S").strftime("%Y-%m-%d %H.%M.%S")
        os.replace(file_dir + folder_name + '\\' + filename, file_dir +  folder_name + '\\' + actual_date + filename[filename.rfind('.'):])
        bar()

if(list_no_exif):
    print(f"The following image{'s' if (len(list_no_exif) > 1) else ''} had no EXIF data and data was created automatically:")
    for i in range(len(list_no_exif)):
        print(list_no_exif[i][0] + "-> Date Taken: " + list_no_exif[i][1])
if(list_no_album):
    print(
        f"The following image{'s' if (len(list_no_exif) > 1) else ''} did not belong to any album and {'were' if (len(list_no_exif) > 1) else 'was'} not organized:")
    for i in range(len(list_no_album)):
        print(list_no_album[i])
print("NOTE: PNG images may use the tag of CreationTime instead of the supplied EXIF. This is accounted for.")

# last_updated_id = photos[0]['id']

# with open('newest_id_file.txt','w') as f:
#     f.write(last_updated_id)





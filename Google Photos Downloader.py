from __future__ import print_function
import time #Measure execution time
import pickle
import os
import requests
import piexif
import pytz
from PIL import Image
from datetime import datetime, timedelta
from dotenv import load_dotenv 
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

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
request = service.mediaItems().list(pageSize=30) #Can modify as needed. Assumes only 30 new photos have been uploaded.
response = request.execute()

photos = response['mediaItems']

last_updated_index = None
last_updated_id = None

with open('newest_id_file.txt') as f:
    last_updated_id = f.read()

#Find the index of the last updated photo
for index, dic in enumerate(photos):
    if dic['id'] == last_updated_id:
        last_updated_index = index
        break
    else:
        last_updated_index = -1
    
photos = photos[:last_updated_index+1] #Slice the list to save space.

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

# print(photos[1]) #DEBUG LINE

start_time = time.time()

#Get a list of photos from each album and put them in a list.
for i in range(len(albums)):
    album_content = []

    for content in get_photos(service, albums[i]['id'],20):
        album_content.append(content)
    
    album_media.append(album_content)
 
album_titles = [] #List of album titles that a certain photo belongs to.

for i in range(last_updated_index+2): # Iterate through each photo.

    #Add the list of album titles that a photo is in to the total list of albums with each index being the index of the photo.
    if(album_titles):
        albums_of_new_photos.append(album_titles)

    album_titles = [] #Reset after each iteration

    #Required since the last iteration will be skipped (hence the last_updated_index+2 in the above).
    if(i == last_updated_index+1):
        break

    for j in range(len(albums)): # Iterate through each album

        #Not sure if this line will be needed at all since sort time might have be too slow or have
        #negligible changes on timing.
        # album_content = sorted(album_content, key = lambda p: datetime.strptime(p['mediaMetadata']['creationTime'], '%Y-%m-%dT%H:%M:%SZ'), reverse=True)
        
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

print(time.time() - start_time)

#Takes care of duo photos here instead of the loop due to ordering issues
albums_of_new_photos  = ["Group Stuff" if len(l) == 2 else l[0] for l in albums_of_new_photos]
print(albums_of_new_photos) #DEBUG line

file_dir = 'C:\\Users\\Tristan Huen\\Desktop\\Temp\\'

#EXIF numerical tag values 
DateTimeOriginal = 36867
DateTimeDigitized = 36868

list_no_exif = []

#Download all photos/videos and change the dates/titles for them to match up
for i in range(last_updated_index+1):
    request = service.mediaItems().get(mediaItemId=photos[i]['id'])
    response = request.execute()
    
    if(albums_of_new_photos[i] == "Videos"):
        media_url = response['baseUrl'] + '=dv' #Need this "=dv" for downloading video properly
    else:
        media_url = response['baseUrl'] + '=d' #Need this "=d" for downloading full quality 

    response = requests.get(media_url)
    photo = response.content

    is_video = False
    no_exif = False
    filename = photos[i]['filename']
    creation_time = photos[i]['mediaMetadata']['creationTime']
    
    with open(file_dir + filename, 'wb') as f:
        f.write(photo)

        if(albums_of_new_photos[i] == "Videos"):
            is_video = True
            pass
        else:
            im = Image.open(file_dir + filename)

            try:
                exif_dict = im.info['exif']
            except KeyError: #Some photos may not have EXIF data
                list_no_exif.append((filename,utc_to_pt(creation_time)))
                no_exif = True
            else:
                #Apply correct date from metadata
                exif_dict = piexif.load(exif_dict)
                actual_date =  utc_to_pt(creation_time)
                encoded_date = actual_date.encode('utf-8')
                exif_dict['Exif'][DateTimeOriginal] = encoded_date
                exif_dict['Exif'][DateTimeDigitized] = encoded_date

                #Apply changes to photos
                exif_bytes = piexif.dump(exif_dict)
                piexif.insert(exif_bytes, file_dir + filename)

    if(is_video):
        #The following uses replace instead of rename since replace accounts for already existing files
        actual_date =  utc_to_pt(creation_time,"%Y-%m-%d %H.%M.%S")
        os.replace(file_dir + filename, file_dir + '\\' + actual_date + filename[filename.find('.'):])
    elif(no_exif):
        actual_date =  utc_to_pt(creation_time)
        exif_dict = {
                    "0th":{},
                    "Exif": {
                        DateTimeOriginal: actual_date,
                        DateTimeDigitized: actual_date
                    },
                    "GPS":{},
                    "Interop":{},
                    "1st":{},
                    "thumbnail":None
        }
        exif_bytes = piexif.dump(exif_dict)
        im.save(file_dir + filename, exif=exif_bytes) #Note this will remove most of the metadata

#Still need to see if the issue of EXIF date not being used can be fixed.
#Could be due to not enough EXIF data being supplied
if(list_no_exif):
    print(f"The following images had no EXIF data and data was created automatically. Date may still need to be modified manually:")
    for i in range(len(list_no_exif)):
        print(list_no_exif[i][0] + "-> Creation Time: " + list_no_exif[i][1])







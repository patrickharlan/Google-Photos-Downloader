from __future__ import print_function
import time #Measure execution time
from datetime import datetime
import pickle
import os.path
import requests
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

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

# AUTH Code Found Here: https://stackoverflow.com/questions/58928685/google-photos-api-python-working-non-deprecated-example

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
request = service.mediaItems().list(pageSize=30)
response = request.execute()

photos = response['mediaItems']

last_updated_index = None
last_updated_id = None
with open('newest_id_file.txt') as f:
    last_updated_id = f.read()

for index, dic in enumerate(photos):
    if dic['id'] == last_updated_id:
        last_updated_index = index
        break
    else:
        last_updated_index = -1
    
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

request = service.albums().list(pageSize=30)
response = request.execute()

albums = response['albums']
print(len(albums))

service._resourceDesc['resources']['mediaItems']['methods']['search']['parameters'].update(search_params)

albums_of_new_photos = []

album_media = []

start_time = time.time()

#Get a list of photos from each album and put them in a list.
for i in range(len(albums)):
    album_content = []

    for content in get_photos(service, albums[i]['id'],20):
        album_content.append(content)
    
    album_media.append(album_content)
album_titles = []

for i in range(last_updated_index+2): # Iterate through each photo

    #Add the list of album titles photo is in to the total list of albums every photo is in
    if(album_titles):
            albums_of_new_photos.append(album_titles)
    album_titles = []

    #Required since the last iteration will be skipped (hence the last_updated_index+2 in the above)
    if(i == last_updated_index+1):
        break

    for j in range(len(albums)): # Iterate through each album

        # Not sure if this line will be needed at all since sort time might be too slow
        #album_content = sorted(album_content, key = lambda p: datetime.strptime(p['mediaMetadata']['creationTime'], '%Y-%m-%dT%H:%M:%SZ'), reverse=True)
        
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

# Filter out the empty lists
print(time.time() - start_time)
albums_of_new_photos  = [["Group Stuff"] if len(l) == 2 else l for l in albums_of_new_photos]
print(albums_of_new_photos)
# file_dir = 'C:\\Users\\Tristan Huen\\Desktop\\Temp\\'

# # for i in range(last_updated_index+1):
# for i in range(2):
#     request = service.mediaItems().get(mediaItemId=photos[i]['id'])
#     response = request.execute()
    
#     photo_url = response['baseUrl']
#     response = requests.get(photo_url)

#     with open(file_dir + photos[i]['filename'], 'wb') as f:
#         f.write(response.content)


# Instagram Notifier  
  
This is a Django project that automatically retrieves posts/stories from specified Instagram accounts and notifies them in real time via LINE Notify + Google Drive backup.  
  
## Features  
  
- Instant notification of images/videos to LINE Notify(posts/stories)  
- Automatic uploading of images/videos to Google Drive(backup)  
- Automatic screenshot acquisition of posts as well  
- Retrieve only the differences of posts/stories  
- Automatic DB logging in case of errors.  
  
---If an error occurs, it will be automatically recorded in the DB.  
  
## Getting started  

### 1. Create environment variables(.env)  
  
INSTAGRAM_USERNAME=target Instagram username  
LINE_NOTIFY_TOKEN=LINE Notify token  
SERVICE_ACCOUNT_FILE=target service_account.json path  
STORY_DRIVE_FOLDER_ID=target Google Drive folder ID(Story)  
POST_DRIVE_FOLDER_ID=target Google Drive folder ID(Post)  
SITE_URL=The public root URL  
  
### 2. Install the required libraries  
```  
$ pip install -r requirements.txt  
```  
  
### 3. Initialize DB    
```  
$ python manage.py makemigrations instagram_notifier   
$ python manage.py migrate  
```  
  
### 4. Run bot  
```  
$ python manage.py instagram_notifier  
```  
  
## License  
Instagram Notifier is under MIT [LICENSE](LICENSE).   

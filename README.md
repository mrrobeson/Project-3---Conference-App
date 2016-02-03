Google App Engine application for the Udacity training course. This application serves up a web api for tracking conferences and conferenc sessions. Users may login with authentication and create conferences, sessions within conferences, and track sessions they wish to attend.

## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]
- 

## Design
- The sessions models were chosen to have a parent conference id in order to be able to track back and retrieve details about the conference in addition to the session. This is necessary because users will want to know which conference a particular session is within, as well as the fact that the project required the api to support the websafeconfkey input in the 'create session' api.
- User wishlist; the user profile model now has session keys stored. This allows the users to add keys for the sessions for which he/she wants to attend and for the application to easily retrieve these.
- In addition to the sessions having a parent conf id, the conference has corresponding associated session keys. These are maintained against the conference for ease of retrieval come query time.
- The featured speaker is new to the conference app. Each session has a speaker associated, while the conference model now has a 'featured speaker' chosen by the cron job simply by looking at the type of session created. If the session created is a keynote, and the conference doesn't already have a featured speaker, the speaker associated with the newly created keynote is set as the featured speaker for that conference.

conference.createConference -	Create new conference.
conference.createSession -	Create new session.
conference.filterPlayground -	Filter Playground
conference.getAnnouncement -	Return Announcement from memcache.
conference.getConference -	Return requested conference (by websafeConferenceKey).
conference.getConferenceSessions -	Return all sessions given a conference.
conference.getConferenceSessionsByType -	Given a conference, return all sessions of a specified type.
conference.getConferencesCreated -	Return conferences created by user.
conference.getConferencesToAttend -	Get list of conferences that user has registered for.
conference.getProfile -	Return user profile.
conference.getSessionsBySpeaker -	Given a speaker, return sesions by speaker across conferences.
conference.getSessionsInWishlist -	Get list of sessions that user has registered for.
conference.queryConferences -	Query for conferences.
conference.querySessions -	Query for sessions.
conference.querySessionsByDate -	Query session objects by date
conference.registerForConference -	Register user for selected conference.
conference.registerForSession -	Add session to user wishlist.
conference.saveProfile -	Update & return user profile.
conference.unregisterFromConference -	Unregister user for selected conference.
conference.unregisterFromSession -	Remove session from user wishlist.
conference.updateConference -	Update conference w/provided fields & return w/updated info.


## Setup Instructions
1. Update the value of `application` in `app.yaml` to the app ID you
   have registered in the App Engine admin console and would like to use to host
   your instance of this sample.
1. Update the values at the top of `settings.py` to
   reflect the respective client IDs you have registered in the
   [Developer Console][4].
1. Update the value of CLIENT_ID in `static/js/app.js` to the Web client ID
1. (Optional) Mark the configuration files as unchanged as follows:
   `$ git update-index --assume-unchanged app.yaml settings.py static/js/app.js`
1. Run the app with the devserver using `dev_appserver.py DIR`, and ensure it's running by visiting your local server's address (by default [localhost:8080][5].)
1. (Optional) Generate your client library(ies) with [the endpoints tool][6].
1. Deploy your application.


[1]: https://developers.google.com/appengine
[2]: http://python.org
[3]: https://developers.google.com/appengine/docs/python/endpoints/
[4]: https://console.developers.google.com/
[5]: https://localhost:8080/
[6]: https://developers.google.com/appengine/docs/python/endpoints/endpoints_tool

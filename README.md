Google App Engine application for the Udacity training course. This application serves up a web api for tracking conferences and conferenc sessions. Users may login with authentication and create conferences, sessions within conferences, and track sessions they wish to attend.

## Products
- [App Engine][1]

## Language
- [Python][2]

## APIs
- [Google Cloud Endpoints][3]
- 

## Instructions

## Design
- The sessions object is created with conf.key as a parent. This is necessary because users will want to know which conference a particular session is within, as well as the fact that the project required the api to support the websafeconfkey input in the 'create session' api.
- User wishlist; the user profile model now has session keys stored. This allows the users to add keys for the sessions for which he/she wants to attend and for the application to easily retrieve these.
- A catch-all session query was created primarily to facilitate testing of the application.
- The featured speaker is new to the conference app. The speaker is stored to the memcache based on leading two or more sessions.

## Enpoints
Services > conference API v1
Authorize requests using OAuth 2.0:


conference.addSessionToWishlist:	Adds a Session to the users's wishlist.
conference.createConference:	Creates a new conference.
conference.createSession:	Creates a new Session.
conference.filterSessionNotTypeByTime:	Returns filtered Sessions which are not type Session and not startTime
conference.getAnnouncement:	Return Announcement from memcache.
conference.getConference:	Return requested conference (by websafeConferenceKey).
conference.getConferenceSessions:	Given a conference, return all sessions
conference.getConferenceSessionsByDate:	Given a conference, return all sessions on specific date
conference.getConferenceSessionsBySpeaker:	Given a conference, return all sessions a certain Speaker
conference.getConferenceSessionsByTime:	Return all sessions starting between startTime and endTime
conference.getConferenceSessionsByType:	Given a conference, return all sessions of a specified type  (eg lecture, keynote, workshop)
conference.getConferencesCreated:	Returns conferences created by the user.
conference.getConferencesToAttend:	Gets list of conferences that the user has registered for.
conference.getFeaturedSpeaker:	Returns featured speaker of a conference from the memcache.
conference.getProfile:	Returns user profile.
conference.getSessionsInWishlist:	Returns the sessions in the users wishlist.
conference.queryConferences:	Query for conferences.
conference.querySessions:	Query for all existing sessions. Primarily used for testing purposes.
conference.registerForConference:	Register user for selected conference.
conference.removeSessionFromWishlist:	Remove session from wishlist.
conference.saveProfile:	Update & return user profile.
conference.unregisterFromConference:	Unregister user for selected conference.
conference.updateConference	Update: conference w/provided fields & return w/updated info.


## Query Question
   Solve this query related problem - say you don't like workshops and sessions after 7PM
   Q:What is the problem with this query and what ways can you solve it?
   A:Problem is that the datastore doesn't handle negative queries. You could
   create a query with filters for the types of session you DO want and for the
   start time you are ok with.
   
   filter(Session.typeOfSession=='Lecture')
   filter(Session.typeOfSession=='Keynote')
   filter(Session.startTime<=19)

## Resources
1. Watched Udacity Scaleable Web Apps course
2. Extensively used the Google App Engine documentation: https://cloud.google.com/appengine/docs
3. Stack Overflow and GAE subreddit for various errors encountered

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

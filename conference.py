#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints

$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $

created by wesc on 2014 apr 21

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'


from datetime import datetime, time, date

import endpoints
import logging

from protorpc import messages
from protorpc import message_types
from protorpc import remote


from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

from models import ConflictException
from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import StringMessage
from models import BooleanMessage
from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import ConferenceQueryForms
from models import TeeShirtSize

from models import Session
from models import SessionForm
from models import SessionForms
from models import SessionType
from models import StringMessage_Featured
from models import SessionQueryForms

from settings import WEB_CLIENT_ID
from settings import ANDROID_CLIENT_ID
from settings import IOS_CLIENT_ID
from settings import ANDROID_AUDIENCE

from utils import getUserId


EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID
MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
ANNOUNCEMENT_TPL = ('Last chance to attend! The following conferences '
                    'are nearly sold out: %s')

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -

DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": [ "Default", "Topic" ],
}

SESSION_DEFAULTS = {
    "highlights": "Not provided",
    "speaker": "Unknown",
    "typeOfSession": "Keynote",
    "venue": "Main Hall",
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!=',
            }

FIELDS =    {
            'CITY': 'city',
            'TOPIC': 'topics',
            'MONTH': 'month',
            'MAX_ATTENDEES': 'maxAttendees',
            }


CONF_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeConferenceKey=messages.StringField(1),
)

SESS_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

SESS_GET_TYPE = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    typeOfSession=messages.EnumField(SessionType, 2)
)

SESS_GET_SPEAKER = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    speaker=messages.StringField(2),
)

SESS_POST_REQUEST = endpoints.ResourceContainer(
    SessionForm,
    websafeConferenceKey=messages.StringField(1),
)

SESS_TO_WISHLIST_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    sessionKey=messages.StringField(1),
)
SESS_IN_WISHLIST_GET_REQUEST = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)

SESS_GET_DATE = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    date=messages.StringField(2),
)

SESS_GET_TIME = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
    startTime=messages.IntegerField(2),
    endTime=messages.IntegerField(3),
)

SESSION_GET_FEATURED_SPEAKER = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeConferenceKey=messages.StringField(1),
)


# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
@endpoints.api(name='conference', version='v1', audiences=[ANDROID_AUDIENCE],
    allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID, ANDROID_CLIENT_ID, IOS_CLIENT_ID],
    scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """Conference API v0.1"""

# - - - Conference objects - - - - - - - - - - - - - - - - -
    def _copyConferenceToForm(self, conf, displayName):
        """Copy relevant fields from Conference to ConferenceForm."""
        cf = ConferenceForm()
        for field in cf.all_fields():
            if hasattr(conf, field.name):
                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(cf, field.name, str(getattr(conf, field.name)))
                else:
                    setattr(cf, field.name, getattr(conf, field.name))
            elif field.name == "websafeKey":
                setattr(cf, field.name, conf.key.urlsafe())
        if displayName:
            setattr(cf, 'organizerDisplayName', displayName)
        cf.check_initialized()
        return cf


    def _createConferenceObject(self, request):
        """Create or update Conference object, returning ConferenceForm/request."""
        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)
        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in DEFAULTS:
            if data[df] in (None, []):
                data[df] = DEFAULTS[df]
                setattr(request, df, DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be same as maxAttendees on creation
        # both for data model & outbound Message
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # generate Profile Key based on user ID and Conference
        # ID based on Profile key get Conference key from ID
        p_key = ndb.Key(Profile, user_id)
        c_id = Conference.allocate_ids(size=1, parent=p_key)[0]
        c_key = ndb.Key(Conference, c_id, parent=p_key)
        data['key'] = c_key
        data['organizerUserId'] = request.organizerUserId = user_id

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()
        taskqueue.add(params={'email': user.email(),
            'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )
        return request


    @ndb.transactional()
    def _updateConferenceObject(self, request):
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        # update existing conference
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        # check that conference exists
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # check that user is owner
        if user_id != conf.organizerUserId:
            raise endpoints.ForbiddenException(
                'Only the owner can update the conference.')

        # Not getting all the fields, so don't create a new object; just
        # copy relevant fields from ConferenceForm to Conference object
        for field in request.all_fields():
            data = getattr(request, field.name)
            # only copy fields where we get data
            if data not in (None, []):
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conf.month = data.month
                # write to Conference object
                setattr(conf, field.name, data)
        conf.put()
        prof = ndb.Key(Profile, user_id).get()
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))


    @endpoints.method(ConferenceForm, ConferenceForm, path='conference',
            http_method='POST', name='createConference')
    def createConference(self, request):
        """Create new conference."""
        return self._createConferenceObject(request)


    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
            path='conference/{websafeConferenceKey}',
            http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """Update conference w/provided fields & return w/updated info."""
        return self._updateConferenceObject(request)


    @endpoints.method(CONF_GET_REQUEST, ConferenceForm,
            path='conference/{websafeConferenceKey}',
            http_method='GET', name='getConference')
    def getConference(self, request):
        """Return requested conference (by websafeConferenceKey)."""
        # get Conference object from request; bail if not found
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        prof = conf.key.parent().get()
        # return ConferenceForm
        return self._copyConferenceToForm(conf, getattr(prof, 'displayName'))


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='getConferencesCreated',
                      http_method='POST', name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """Return conferences created by user."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        user_id = getUserId(user)

        # create ancestor query for all key matches for this user
        confs = Conference.query(ancestor=ndb.Key(Profile, user_id))
        prof = ndb.Key(Profile, user_id).get()
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, getattr(prof, 'displayName')) for conf in confs])


    def _getQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Conference.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        for filtr in filters:
            if filtr["field"] in ["month", "maxAttendees"]:
                filtr["value"] = int(filtr["value"])
            formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
            q = q.filter(formatted_query)
        return q


    def _formatFilters(self, filters):
        """Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None

        for f in filters:
            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}

            try:
                filtr["field"] = FIELDS[filtr["field"]]
                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator.")

            # Every operation except "=" is an inequality
            if filtr["operator"] != "=":
                # check if inequality operation has been used in previous filters
                # disallow the filter if inequality was performed on a different field before
                # track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on only one field.")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)


    @endpoints.method(ConferenceQueryForms, ConferenceForms,
                      path='queryConferences',
                      http_method='POST', name='queryConferences')
    def queryConferences(self, request):
        """Query for conferences."""
        conferences = self._getQuery(request)

        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return ConferenceForms(
                items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) for conf in \
                conferences]
        )


    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                      path='conferences/attending',
                      http_method='GET', name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """Get list of conferences that user has registered for."""
        prof = self._getProfileFromUser() # get user Profile
        conf_keys = [ndb.Key(urlsafe=wsck) for wsck in prof.conferenceKeysToAttend]
        conferences = ndb.get_multi(conf_keys)

        # get organizers
        organisers = [ndb.Key(Profile, conf.organizerUserId) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        # put display names in a dict for easier fetching
        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, names[conf.organizerUserId])
                                  for conf in conferences])



# - - - Profile objects - - - - - - - - - - - - - - - - - - -
    def _copyProfileToForm(self, prof):
        """Copy relevant fields from Profile to ProfileForm."""
        # copy relevant fields from Profile to ProfileForm
        pf = ProfileForm()
        for field in pf.all_fields():
            if hasattr(prof, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(pf, field.name, getattr(TeeShirtSize, getattr(prof, field.name)))
                else:
                    setattr(pf, field.name, getattr(prof, field.name))
        pf.check_initialized()
        return pf


    def _getProfileFromUser(self):
        """Return user Profile from datastore, creating new one if non-existent."""
        # make sure user is authed
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get Profile from datastore
        user_id = getUserId(user)
        p_key = ndb.Key(Profile, user_id)
        profile = p_key.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key = p_key,
                displayName = user.nickname(),
                mainEmail= user.email(),
                teeShirtSize = str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()

        return profile      # return Profile


    def _doProfile(self, save_request=None):
        """Get user Profile and return to user, possibly updating it first."""
        # get user Profile
        prof = self._getProfileFromUser()

        # if saveProfile(), process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(prof, field, str(val))
                        #if field == 'teeShirtSize':
                        #    setattr(prof, field, str(val).upper())
                        #else:
                        #    setattr(prof, field, val)
                        prof.put()

        # return ProfileForm
        return self._copyProfileToForm(prof)


    @endpoints.method(message_types.VoidMessage, ProfileForm,
                      path='profile',
                      http_method='GET', name='getProfile')
    def getProfile(self, request):
        """Return user profile."""
        return self._doProfile()


    @endpoints.method(ProfileMiniForm, ProfileForm,
                      path='profile',
                      http_method='POST', name='saveProfile')
    def saveProfile(self, request):
        """Update & return user profile."""
        return self._doProfile(request)



# - - - Announcements - - - - - - - - - - - - - - - - - - - -
    @staticmethod
    def _cacheAnnouncement():
        """Create Announcement & assign to memcache; used by
        memcache cron job & putAnnouncement().
        """
        confs = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if confs:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = ANNOUNCEMENT_TPL % (
                ', '.join(conf.name for conf in confs))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement


    @endpoints.method(message_types.VoidMessage, StringMessage,
                      path='conference/announcement/get',
                      http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """Return Announcement from memcache."""
        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")



# - - - Registration - - - - - - - - - - - - - - - - - - - -
    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """Register or unregister user for selected conference."""
        retval = None
        prof = self._getProfileFromUser() # get user Profile

        # check if conf exists given websafeConfKey
        # get conference; check that it exists
        wsck = request.websafeConferenceKey
        conf = ndb.Key(urlsafe=wsck).get()
        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % wsck)

        # register
        if reg:
            # check if user already registered otherwise add
            if wsck in prof.conferenceKeysToAttend:
                raise ConflictException(
                    "You have already registered for this conference")

            # check if seats avail
            if conf.seatsAvailable <= 0:
                raise ConflictException(
                    "There are no seats available.")

            # register user, take away one seat
            prof.conferenceKeysToAttend.append(wsck)
            conf.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if wsck in prof.conferenceKeysToAttend:

                # unregister user, add back one seat
                prof.conferenceKeysToAttend.remove(wsck)
                conf.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()
        conf.put()
        return BooleanMessage(data=retval)


    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='POST', name='registerForConference')
    def registerForConference(self, request):
        """Register user for selected conference."""
        return self._conferenceRegistration(request)


    @endpoints.method(CONF_GET_REQUEST, BooleanMessage,
                      path='conference/{websafeConferenceKey}',
                      http_method='DELETE', name='unregisterFromConference')
    def unregisterFromConference(self, request):
        """Unregister user for selected conference."""
        return self._conferenceRegistration(request, reg=False)



# - - - Session - - - - - - - - - - - - - - - - - - -
    def _copySessionToForm(self, sess):
        """Copy relevant fields from Session to SessionForm."""

        sf = SessionForm()
        for field in sf.all_fields():
            if hasattr(sess, field.name):
                if field.name == 'date':
                    sf.date = str(sess.date)
                elif field.name == 'startTime':
                    sf.startTime = str(sess.startTime)
                elif field.name == 'endTime':
                    sf.endTime = str(sess.endTime)
                elif field.name == 'duration':
                    sf.endTime = str(sess.endTime)
                elif field.name == 'typeOfSession':
                    try:
                        setattr(sf, field.name, getattr(SessionType, getattr(sess, field.name)))
                    except AttributeError:
                        setattr(sf, field.name, getattr(SessionType, 'NOT_SPECIFIED'))
                else:
                    setattr(sf, field.name, getattr(sess, field.name))
        sf.websafeKey = sess.key.urlsafe()
        sf.check_initialized()

        return sf


    def _createSessionObject(self, request):
        """Create or update Session object, returning SessionForm/request."""

        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        # get user ID (email)
        user_id = getUserId(user)

        if not request.name:
            raise endpoints.BadRequestException("Session 'name' field required")

        #get session key
        conf = ndb.Key(urlsafe=request.websafeConferenceKey).get()

        #get conference organizer ID (email) and compare with current user ID
        conf_organizer_id = conf.key.parent().id()
        if user_id != conf_organizer_id:
            raise endpoints.BadRequestException("Only the Conference Organizer able to create Session")

        if not conf:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        new_id = Session.allocate_ids(size=1, parent=conf.key)[0]
        s_key = ndb.Key(Session, new_id, parent=conf.key)

        #get data
        data = {field.name: getattr(request, field.name) for field in request.all_fields() if field.name != "websafeConferenceKey"}
        del data['websafeKey']

        # add default values for those missing (both data model & outbound Message)
        for df in SESSION_DEFAULTS:
            if data[df] in (None, []):
                data[df] = SESSION_DEFAULTS[df]
                setattr(request, df, SESSION_DEFAULTS[df])

        if data['date']:
            data['date'] = datetime.strptime(data['date'][:10], "%Y-%m-%d").date()
        if data['startTime']:
            data['startTime'] = int(data['startTime'])
        if data['endTime']:
            data['endTime'] = int(data['endTime'])
        if data['duration']:
            data['duration'] = int(data['duration'])
        data['typeOfSession'] = str(data['typeOfSession'])
        data['key'] = s_key

        # store Session data & return (modified) SessionForm
        Session(**data).put()

        # set memcache for featured speaker and session
        if data['speaker'] and data['speaker'] != "Unknown":
            taskqueue.add(params={'websafeConferenceKey': request.websafeConferenceKey,
                                  'speaker': data['speaker']},
                          url='/tasks/set_featured_speaker')

        return self._copySessionToForm(s_key.get())


    @endpoints.method(SESS_POST_REQUEST, SessionForm,
                      path='/conference/{websafeConferenceKey}/createsession',
                      http_method='POST', name='createSession')
    def createSession(self, request):
        """Create new Session."""
        return self._createSessionObject(request)


    @endpoints.method(SESS_GET_REQUEST, SessionForms,
                      path='/conference/{websafeConferenceKey}/session',
                      http_method='GET', name='getConferenceSessions')
    def getConferenceSessions(self, request):
        """Given a conference, return all sessions"""

        # #get conference key
        conference_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        if not conference_key:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)
        sessions_all = Session.query(ancestor=conference_key)

        return SessionForms(items=[self._copySessionToForm(sess) for sess in sessions_all])


    @endpoints.method(SESS_GET_TYPE, SessionForms,
                      path='/conference/{websafeConferenceKey}/session/type/{typeOfSession}',
                      http_method='GET', name='getConferenceSessionsByType')
    def getConferenceSessionsByType(self, request):
        """Given a conference, return all sessions of a specified type 
        (eg lecture, keynote, workshop)
        """

        #get conference key
        conference_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        if not conference_key:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        sessions_all = Session.query(ancestor=conference_key)
        sessions_ByType = sessions_all.filter(Session.typeOfSession == request.typeOfSession.name)

        return SessionForms(items=[self._copySessionToForm(sess) for sess in sessions_ByType])


    @endpoints.method(SESS_GET_SPEAKER, SessionForms,
            path='/conference/{websafeConferenceKey}/session/speaker/{speaker}',
            http_method='GET', name='getConferenceSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """Given a conference, return all sessions for by Speaker"""

        #get conference key
        conference_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        if not conference_key:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        sessions_all = Session.query(ancestor=conference_key)
        sessions_BySpeaker = sessions_all.filter(Session.speaker == request.speaker)

        return SessionForms(items=[self._copySessionToForm(sess) for sess in sessions_BySpeaker]
        )


    @endpoints.method(SESS_GET_DATE, SessionForms,
                      path='/conference/{websafeConferenceKey}/session/date/{date}',
                      http_method='GET', name='getConferenceSessionsByDate')
    def getConferenceSessionsByDate(self, request):
        """Given a conference, return all sessions on specific date"""

        #get conference key
        conference_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        if not conference_key:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # transform {date} into date format
        date = datetime.strptime(request.date, '%Y-%m-%d').date()
        print("date: ", date)

        # get sessions on this date
        sessions_all = Session.query(ancestor=conference_key)
        sessions_ByDate = sessions_all.filter(Session.date == date)

        return SessionForms(items=[self._copySessionToForm(sess) for sess in sessions_ByDate]
        )


    @endpoints.method(SESS_GET_TIME, SessionForms,
                      path='/conference/{websafeConferenceKey}/session/time/{startTime}/{endTime}',
                      http_method='GET', name='getConferenceSessionsByTime')
    def getConferenceSessionsByTime(self, request):
        """Return all sessions starting between startTime and endTime"""

        # #get conference key
        conference_key = ndb.Key(urlsafe=request.websafeConferenceKey)
        if not conference_key:
            raise endpoints.NotFoundException(
                'No conference found with key: %s' % request.websafeConferenceKey)

        # get sessions for conference in a time range
        sessions_all = Session.query(ancestor=conference_key)
        sessions_ByTime = sessions_all.filter(ndb.AND(Session.startTime >= request.startTime, Session.startTime <= request.endTime))

        return SessionForms(items=[self._copySessionToForm(sess) for sess in sessions_ByTime]
        )

    def _getSessionQuery(self, request):
        """Return formatted query from the submitted filters."""
        q = Session.query()
        inequality_filter, filters = self._formatFilters(request.filters)

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Session.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Session.name)

        # for filtr in filters:
        #     if filtr["field"] in ["month", "maxAttendees"]:
        #         filtr["value"] = int(filtr["value"])
        #     formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
        #     q = q.filter(formatted_query)
        return q    

    @endpoints.method(SessionQueryForms, SessionForms,
                      path='querySessions',
                      http_method='POST', name='querySessions')
    def querySessions(self, request):
        """Query for sessions."""
        sessions = self._getSessionQuery(request)

        # # need to fetch organiser displayName from profiles
        # # get all keys and use get_multi for speed
        # organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        # profiles = ndb.get_multi(organisers)

        # # put display names in a dict for easier fetching
        # names = {}
        # for profile in profiles:
        #     names[profile.key.id()] = profile.displayName

        # return individual ConferenceForm object per Conference
        return SessionForms(
                items=[self._copySessionToForm(sess) for sess in \
                sessions]
        )

# - - - User Wishlist - - - - - - - - - - - - - - - - - - -
    @endpoints.method(SESS_TO_WISHLIST_GET_REQUEST, BooleanMessage,
                      path='session/{sessionKey}',
                      http_method='POST', name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """Add a Session To Wishlist."""
        return self._updateWishlist(request)


    @endpoints.method(SESS_TO_WISHLIST_GET_REQUEST, BooleanMessage,
                      path='session/{sessionKey}',
                      http_method='DELETE', name='removeSessionFromWishlist')
    def removeSessionFromWishlist(self, request):
        """Remove session from wishlist."""
        return self._updateWishlist(request, add=False)


    @ndb.transactional(xg=True)
    def _updateWishlist(self, request, add=True):
        """Create or update Session object, returning SessionForm/request."""

        # preload necessary data items
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        prof = self._getProfileFromUser()

        session_key = request.sessionKey
        session = ndb.Key(urlsafe=session_key).get()
        if not session:
            raise endpoints.NotFoundException(
                'No session found with key: %s' % session)

        # add to wishlist
        if add:
            # check if session is already registered otherwise add
            if session_key in prof.sessionKeysInWishlist:
                raise ConflictException(
                    "You have already added this session to your wishlist")

            if prof.sessionKeysInWishlist is None:
                prof.sessionKeysInWishlist[0] = session_key
            else:
                prof.sessionKeysInWishlist.append(session_key)
            retval = True

        # remove
        else:
            # check if session already in wishlist and remove
            if session_key in prof.sessionKeysInWishlist:
                prof.sessionKeysInWishlist.remove(session_key)
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        prof.put()

        return BooleanMessage(data=retval)


    @endpoints.method(SESS_IN_WISHLIST_GET_REQUEST, SessionForms,
                      path='session/wishlist',
                      http_method='GET', name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """Get list of Sessions that user wish to attend

            1)return a wishlist of sessions for a specific conference if
                with key = {websafeConferenceKey}
            2) return a wishlist of all sessions over all conferences use
                added to a whishlist if {websafeConferenceKey} is None
        """

        # get user Profile
        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')
        prof = self._getProfileFromUser()

        # show all sessions for all conferences to attend
        session_wishlist_keys = [ndb.Key(urlsafe=session_key) for session_key in prof.sessionKeysInWishlist]
        sessions_wishlist = ndb.get_multi(session_wishlist_keys)

        # if user wants to see selected session for a specific conference
        # use {websafeConferenceKey} to select them
        if request.websafeConferenceKey is not None:
            output = []
            conference_key = ndb.Key(urlsafe=request.websafeConferenceKey)
            for item in session_wishlist_keys:
                if item.parent() == conference_key:
                    print("item.parent: ", item.parent())
                    output.append(item)
            sessions_wishlist = ndb.get_multi(output)
            return SessionForms(items=[self._copySessionToForm(sess)
                                   for sess in sessions_wishlist])

        # return set of SessionForm objects
        return SessionForms(items=[self._copySessionToForm(sess)
                                   for sess in sessions_wishlist])


# - - - Featured Speaker - - - - - - - - - - - - - - - - - - -
    @staticmethod
    def setFeaturedSpeaker(websafeConferenceKey, speaker):
        """
        Check a speaker in a memcache for featured speaker
        and set him to the memcache if he is a speaker for at least 2 sessions
        """

        conf_key = ndb.Key(urlsafe=websafeConferenceKey)
        sessions = Session.query(Session.speaker == speaker, ancestor=conf_key)
        if sessions.count() > 1:
            featuredSpeaker_cache = "%s is a featured speaker for %s sessions!" % (speaker, sessions.count())
            memcache.set(websafeConferenceKey, featuredSpeaker_cache)


    @endpoints.method(SESSION_GET_FEATURED_SPEAKER, StringMessage,
            path='conference/{websafeConferenceKey}/session/speaker/featured',
            http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """Return featured speaker of a conference from memcache"""

        # get conference key
        MEMCACHE_FEATURED_KEY = request.websafeConferenceKey
        FeaturedSpeakers = memcache.get(MEMCACHE_FEATURED_KEY)
        if not FeaturedSpeakers:
            FeaturedSpeakers = ''  # return empty speaker form on failure for no results

        return StringMessage(data=FeaturedSpeakers)


# - - - Session Inaquality Filter - - - - - - - - - - - - - - - - - - -

    SESS_FILTER_TYPE_TIME = endpoints.ResourceContainer(
        message_types.VoidMessage,
        websafeConferenceKey=messages.StringField(1),
        typeOfSession=messages.EnumField(SessionType, 2),
        startTime=messages.IntegerField(3),
    )

    @endpoints.method(SESS_FILTER_TYPE_TIME, SessionForms,
            path='conference/{websafeConferenceKey}/session/{typeOfSession}/time/{startTime}',
            http_method='GET', name='filterSessionNotTypeByTime')
    def filterSessionNotTypeByTime(self, request):
        """Return filtered Sessions which are != type of Session and
        != startTime
        """

        type = str(request.typeOfSession)
        sessions_noType = Session.query(ndb.OR(Session.typeOfSession < str(type),
										Session.typeOfSession > str(type)))
        sessions = [sess for sess in sessions_noType if sess.startTime <= request.startTime]

        return SessionForms(items=[self._copySessionToForm(sess)
                                   for sess in sessions])

api = endpoints.api_server([ConferenceApi]) # register API

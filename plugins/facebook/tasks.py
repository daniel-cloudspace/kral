import urllib2,json
from celery.task import PeriodicTask, Task
from datetime import datetime
from models import FacebookUser, FacebookPost
from celery.execute import send_task 
from kral.tasks import *
from kral.models import *

class Facebook(Task):
    def run(self, querys, **kwargs):
        for query in querys:
            FacebookFeed.delay(query)        

class FacebookFeed(Task):
    def run(self, query, **kwargs):
        logger = self.get_logger(**kwargs)
        logger.debug("Executing every 10 seconds...")
        url = "https://graph.facebook.com/search?q=%s&type=post&limit=100" % query
        try:
            data = json.loads(urllib2.urlopen(url).read())
        except Exception, e:
            return
        paging = data['paging'] #next page / previous page urls
        items = data['data']
        for item in items:
            ProcessFBPost.delay(item,query)
        return "Checking Feed"
   
class ProcessFBPost(Task):
    def run(self, item, query, **kwargs):
        logger = self.get_logger(**kwargs)
        time_format = "%Y-%m-%dT%H:%M:%S+0000"
        data, from_user, to_users = {}, {}, {}
        if item.has_key('properties'): item.pop('properties') 
        if item.has_key('application'):
            application = item['application']
            if application:
                data['application_name'] = application['name']
                data['application_id'] = application['id']
            item.pop('application') 

        if item.has_key('likes'):
            data['likes'] = item['likes']['count']
            item.pop('likes')
        
        #build fields/attrib dict to unpack to model - do some name mangling to fit model fields
        for k,v in item.items():
            if k == 'id':
                data.update({'post_id': v })
            elif k == 'from':
                from_user = item.pop('from') 
            elif k == 'to':
                to_users = item.pop('to')
            elif k == 'created_time':
                data.update({ k : datetime.strptime(v, time_format)})
            elif k == 'updated_time':
                data.update({ k : datetime.strptime(v, time_format)})
            else:
                data.update({ k : v })

        fbpost, created = FacebookPost.objects.get_or_create(**data)
        if created:
            logger.debug("Saved new FacebookPost: %s" % fbpost)

        #hand off url to be processed
        if fbpost.link:
            send_task("kral.tasks.ExpandURL", [fbpost.link])

        #store relations
        if from_user:
            fbuser, created = FacebookUser.objects.get_or_create(
                user_id = from_user['id'],
                name = from_user['name'],
            )
            if created:
                logger.debug("Saved new FacebookUser: %s" % fbuser)
            fbpost.from_user =  fbuser

        if to_users:
            for user in to_users['data']:
                fbuser, created = FacebookUser.objects.get_or_create(
                    user_id = user['id'], 
                    name = user['name'],
                )
                fbpost.to_users.add(fbuser)

        fbpost.save()
        qobj = Query.objects.get(text__iexact=query)
        fbpost.querys.add(qobj)
        print "Added relation: %s" % qobj
        return "Saved Post/User"
# vim: ai ts=4 sts=4 et sw=4

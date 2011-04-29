import os
import re
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.scc import models

db_repo = models.Repository.objects.get_or_create(slug='linux')[0]

# Email regular expression modified from django.core.validators.email_re
email_re = re.compile(
    r"([-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"
    r'|"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\'
    r'[\001-011\013\014\016-\177])*")'
    r'@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?',
    re.IGNORECASE)

# Restrict all of the RawAuthor objects to be from the current repository
rawauthor_qs = models.RawAuthor.objects.filter(repository=db_repo)

# Create an email lookup to a list of RawAuthors
author_email_dict = {}
for rawauthor in rawauthor_qs.exclude(email=''):
    if rawauthor.email in author_email_dict:
        author_email_dict[rawauthor.email].append(rawauthor)
    else:
        author_email_dict[rawauthor.email] = [rawauthor]

# Attempt to fix people who put their email in the name field
for rawauthor in rawauthor_qs.filter(email=''):
    match = email_re.search(rawauthor.name)
    if match:
        email = match.group(0)
        print email
        if email in author_email_dict:
            author_email_dict[email].append(rawauthor)
        else:
            author_email_dict[email] = [rawauthor]

# Create a name lookup to a list of emails
author_name_dict = {}
for rawauthor in rawauthor_qs.all():
    name = rawauthor.name
    if name != "":
        email = rawauthor.email
        if name in author_name_dict:
            author_name_dict[name].append(email)
        else:
            author_name_dict[name] = [email]

# Merge the rawauthors in the email dict until there's no more
# Note: If an rawauthor still has no corresponding author there are two cases,
#       1) they have an email and no name (rawauthors still in email_dict after
#          the break
#       2) they have no email and an unmerged name (the rawauthor was never in
#          email_dict)
while len(author_email_dict) > 0:
    try:
        name_stack = [author_name_dict.iterkeys().next()]
    # We ran out of names, but there are still some emails unaccounted for
    except StopIteration:
        break
    rawauthors = []
    # Go until we run out of names to merge
    while len(name_stack) > 0:
        name = name_stack.pop()
        if name in author_name_dict:
            # Get all the emails associated with this name
            for email in author_name_dict[name]:
                # Claim the email for this author and remove it from email_dict
                if email in author_email_dict:
                    email_rawauthors = author_email_dict[email]
                    del author_email_dict[email]
                    # Add any non-duplicate names to the name_stack
                    for rawauthor in email_rawauthors:
                        if name != rawauthor.name:
                            name_stack.append(rawauthor.name)
                    # Merge the rawauthors
                    rawauthors += email_rawauthors
            del author_name_dict[name]

    # If we're merging
    if len(rawauthors) > 0:
        rawcommits_qs = models.RawCommit.objects.filter(author__in=rawauthors)
        recent_commit = rawcommits_qs.order_by("-utc_time")[0]
        recent_rawauthor = recent_commit.author

        # Ensure all the authors are the same
        author = rawauthors[0].author
        for rawauthor in rawauthors[1:]:
            assert author == rawauthor.author

        # They don't have an author, so create one
        if not author:
            author = models.Author.objects.create(name=recent_rawauthor.name,
                                                  email=recent_rawauthor.email)
            for rawauthor in rawauthors:
                rawauthor.author = author
                rawauthor.save()

def manual_merge_email_to_name(email, name):
    try:
        rawauthor = rawauthor_qs.filter(author__isnull=True).get(email=email)
    # We already added the author or it actually doesn't exist, so just return
    except models.RawAuthor.DoesNotExist:
        return

    merge_rawauthor_qs = rawauthor_qs.filter(name=name)
    if merge_rawauthor_qs.count() > 0:
        author = merge_rawauthor_qs[0].author
        assert author != None
    else:
        author = models.Author.objects.create(name=name, email=email)

    rawauthor.author = author
    rawauthor.save()
    # print "Manual merge of rawauthor %d successful" % rawauthor.pk

manual_merge_email_to_name("jejb@titanic.il.steeleye.com", "James Bottomley")
manual_merge_email_to_name("jketreno@io.(none)", "James Ketrenos")
manual_merge_email_to_name("greg@echidna.(none)", "Greg Kroah-Hartman")
manual_merge_email_to_name("felipewd@terra.com.br", "Felipe W Damasio")

for rawauthor in rawauthor_qs.filter(author__isnull=True).all():
    author = models.Author.objects.create(name=rawauthor.name,
                                          email=rawauthor.email)
    rawauthor.author = author
    rawauthor.save()
    # print "Unknown rawauthor %d" % rawauthor.pk

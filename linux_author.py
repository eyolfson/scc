import os
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.repositories.models import *

# def init_author(name, email):
#     # Need a lock so we don't get 2 entries with the same e-mail
#     return author


#         try:
#             author = models.Author.objects.get(repository=django_repository, email=email)
#             if args.debug and author.name != name:
#                 log("Author('%s', '%s') ignoring name '%s'" % (author.name, email, name))
#         except:
#             author = models.Author.objects.create(repository=django_repository, name=name, email=email)


linux_authors = {}
blank_names = []

for a in Author.objects.filter(repository__pk=1):
    if a.name == '':
        blank_names.append(a)
    else:
        if a.name in linux_authors:
            linux_authors[a.name].append(a)
        else:
            linux_authors[a.name] = [a]

# import codecs
# author_list = [x for x in linux_authors.iteritems()]
# author_list.sort()

# file = codecs.open("temp.txt", "w", "utf-8")
# def f(x):
#     file.write("%s <%s>\n" % (x.name, x.email))
# for (key, value) in author_list:
#     file.write("%s\n" % key)
#     file.write('===\n')
#     map(f, value)
#     file.write('\n')
# file.close()


# for (key,value) in linux_authors.iteritems():
#     la = LinuxAuthor.objects.create()
#     for a in value:
#         la.authors.add(a)

# for a in blank_names:
#     la = LinuxAuthor.objects.create()
#     la.authors.add(a)


print len(LinuxAuthor.objects.all())

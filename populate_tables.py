import argparse
import codecs
from datetime import datetime, timedelta
import difflib
import git
import multiprocessing
import os
from pytz import timezone, utc
import re
import shutil
import sys
import threading

# Set the path
path = '/home/jon/git/scc-web'
if path not in sys.path:
    sys.path.append(path)
path = '/home/jon/git/scc-web/scc_website'
if path not in sys.path:
    sys.path.append(path)
del path

# Import the Django models
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.scc import models

# Command line parser
parser = argparse.ArgumentParser(description="Python script to populate the SCC database tables.")
parser.add_argument("slug", help="unique name for the repository (eg. linux)")
parser.add_argument("directory", nargs='?', help="directory of the git repository")
parser.add_argument("encoding", nargs='?', help="encoding of the git repository")
parser.add_argument("--verify-additions", action='store_true', help="enable verification of commit additions")
parser.add_argument("--merge-authors", action='store_true', help="enable merging of authors")
parser.add_argument("--adjust-timezones", action='store_true', help="enable fixing of timezones")
parser.add_argument("--log", action='store_true', help="enable logging")
parser.add_argument("--skip-merge", action='store_true', help="skip author merging")
parser.add_argument("--skip-manual-fixes", action='store_true', help="skip manual fixes")
args = parser.parse_args()

LOG_DIRECTORY = 'log'
SLUG = args.slug
CORE = args.directory is not None
VERIFY_ADDITIONS = args.verify_additions
MERGE_AUTHORS = args.merge_authors
ADJUST_TIMEZONES = args.adjust_timezones
LOG = args.log

# Open the log file
if LOG:
    if not os.path.exists(LOG_DIRECTORY):
        os.mkdir(LOG_DIRECTORY)
    # filename = "%s.log" % datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    filename = "scc.log"
    log_file = codecs.open(os.path.join(LOG_DIRECTORY, filename), "w", "utf-8")
    del filename

# Logging function
def log(msg):
    if LOG:
        time_stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
        log_file.write("[%s] %s\n" % (time_stamp, msg))
        log_file.flush()

def previous_revision(sha1):
    return "%s~1" % sha1

def unified_diff(git_commit, init, update, fini, continue_check=None):
    # An exception occurs if this commit does not have any previous commits
    try:
        # NOTE: Rename detection doesn't seem to work, maybe a bug with
        # GitPython?
        diffs = git_commit.diff(previous_revision(git_commit.hexsha))
        for diff in diffs:
            # This diff is a deleted or new file, so ignore it
            if diff.deleted_file or diff.new_file:
                continue

            assert diff.a_blob.path == diff.b_blob.path
            filename = diff.a_blob.path

            context = {}
            context = init(filename, context)

            if continue_check:
                if continue_check(context):
                    continue

            # Read the data and get the lines (yes I know it seems backwards) and
            # remove Windows' stupid newline character which messes things up on
            # UNIX
            previous_lines = diff.b_blob.data_stream.read().replace("\r","").splitlines()
            current_lines = diff.a_blob.data_stream.read().replace("\r","").splitlines()
            
            # Compute the unified diff, and throw away the first two file
            # information lines
            iter_diff = difflib.unified_diff(previous_lines, current_lines)
            for i in xrange(2):
                try:
                    iter_diff.next()
                except StopIteration:
                    break

            # Update the context from the unified diff
            for line in iter_diff:
                context = update(line, context)

            # Final call
            fini(filename, context)
    except:
        pass

def get_or_create_db_commit(git_commit):
    sha1 = git_commit.hexsha

    # Get name and email
    name = u""
    if git_commit.author.name:
        name = git_commit.author.name
    email = ""
    if git_commit.author.email:
        email = git_commit.author.email

    # Create raw author
    lock_raw_author.acquire()
    db_raw_author = models.RawAuthor.objects.get_or_create(repository=db_repository, name=name, email=email)[0]
    lock_raw_author.release()

    # Get the additional data
    merge = len(git_commit.parents) > 1
    utc_time = datetime.utcfromtimestamp(git_commit.authored_date)
    local_time = datetime.utcfromtimestamp(git_commit.authored_date - git_commit.author_tz_offset)

    # Try to get the commit from the database, or create it
    lock_commit.acquire()
    try:
        db_commit = models.Commit.objects.get(repository=db_repository, sha1=sha1)
        created = False

        # Check to see if we need to verify the additions
        if VERIFY_ADDITIONS:
            if sha1 in verified_additions:
                verified = True
            else:
                verified = False
                verified_additions[sha1] = True


    except models.Commit.DoesNotExist:
        db_commit = models.Commit.objects.create(
            repository=db_repository,
            raw_author=db_raw_author,
            sha1=sha1,
            merge=merge,
            utc_time=utc_time,
            local_time=local_time)
        created = True
        if VERIFY_ADDITIONS:
            verified = False
            verified_additions[sha1] = True
    finally:
        lock_commit.release()

    # Don't include any data for merges
    if merge:
        return db_commit

    # We assume if we don't have to verify anything and we didn't just create it, we're done
    if not (created or (VERIFY_ADDITIONS and not verified)):
        return db_commit

    # Define the functions needed for the diff
    def init(filename, context):
        context['lines_code'] = 0
        context['lines_comments'] = 0
        context['lines_other'] = 0
        if re_c_file.search(filename):
            context['is_c_file'] = True
        else:
            context['is_c_file'] = False
        return context

    def update(line, context):
        # We're just keeping track of how many lines changed, which are all additions in the
        # unified diff
        if line.startswith("+"):
            if context['is_c_file']:
                if not re_c_file_comment.match(line[1:]):
                    context['lines_code'] += 1
                else:
                    context['lines_comments'] += 1
            else:
                context['lines_other'] += 1
        return context

    def fini(filename, context):
        # Get the file representation in the database
        lock_file.acquire()
        db_file = models.File.objects.get_or_create(repository=db_repository, name=filename)[0]
        lock_file.release()

        # If it already exists, update it, otherwise create it
        try:
            db_commit_file_addition = models.CommitFileAddition.objects.get(commit=db_commit, file=db_file)
            db_commit_file_addition.lines_code = context['lines_code']
            db_commit_file_addition.lines_comments = context['lines_comments']
            db_commit_file_addition.lines_other = context['lines_other']
            db_commit_file_addition.save()
        except models.CommitFileAddition.DoesNotExist:
            models.CommitFileAddition.objects.create(
                commit=db_commit,
                file=db_file,
                lines_code = context['lines_code'],
                lines_comments = context['lines_comments'],
                lines_other = context['lines_other']
            )

    # Do the unified diff
    unified_diff(git_commit, init, update, fini)
    return db_commit

class SCCThread(threading.Thread):

    def __init__(self, id):
        threading.Thread.__init__(self)
        self.id = id

        # Copy the repository, if needed
        copy_directory = "work/%s-%d" % (SLUG, id)
        if not os.path.exists(copy_directory):
            self.log("Copying '%s' to '%s'" % (directory, copy_directory))
            shutil.copytree(directory, copy_directory, symlinks=True)
            self.log("Copying finished")

        self.git_repository = git.Repo(copy_directory, odbt=git.GitCmdObjectDB)
        self.git = git.Git(copy_directory)
        self._current_branch = "scc_left"
        self._free_branch = "scc_right"
        self.git.checkout(["-b", self._current_branch, "master"])
 
    def log(self, message):
        lock_log.acquire()
        try:
            log("<T%d> %s" % (self.id, message))
        finally:
            lock_log.release()

    def switch_to_revision(self, revision):
        self.git.checkout(["-b", self._free_branch, revision])
        self._current_branch, self._free_branch = self._free_branch, self._current_branch # Swap
        self.git.branch(["-D", self._free_branch])

    def analyze(self, git_commit):
        db_commit = get_or_create_db_commit(git_commit)
        sha1 = db_commit.sha1

        # Set the first commit to the earliest commit without parents
        if len(git_commit.parents) == 0:
            lock_repository.acquire()
            if db_repository.first_commit:
                if db_current_commit.utc_time < db_repository.first_commit.utc_time:
                    db_repository.first_commit = db_commit
                    db_repository.save()
                    self.log('Changed "first_commit" to %s.' % sha1)
            else:
                db_repository.first_commit = db_commit
                db_repository.save()
                self.log('Set "first_commit" to %s.' % sha1)
            lock_repository.release()

        # Ignore any merges or commits which are not fixes
        if db_commit.merge or not re_fixing_commit_message.search(git_commit.message):
            return

        # Create the fixing commit
        db_fixing_commit = models.FixingCommit.objects.get_or_create(commit=db_commit)[0]

        def init(filename, context):
            context['blame_lines'] = []
            if re_c_file.search(filename):
                context['is_c_file'] = True
            else:
                context['is_c_file'] = False
            return context

        # If this is not a c file, just continue to the next iteration
        def continue_check(context):
            if context['is_c_file']:
                return False
            return True

        def update(line, context):
            # Remember: only the previous file's line number matters when we do the
            # blaming, so we only need to record that
            # We can ignore the next add line if the line before it was a removal
            # otherwise, we cannot.
            # If we're in an add block and not ignoring we look for the first line
            # added which is not a comment; in this case add the current line number
            # to the blame (which is the line before the add block in the previous
            # file) and ignore the rest of the block.
            if line.startswith("@@"):
                match = re_unified_diff_line_numbers.match(line)
                # Subtract one so our increment on the next line is correct
                context['line_number'] = int(match.group(1)) - 1
                # We should ignore here, because there's no context before
                context['ignore_next_add'] = True
            elif line.startswith("-"):
                context['line_number'] += 1
                if not re_c_file_comment.match(line[1:]):
                    context['blame_lines'].append((context['line_number'], True))
                # TODO: Actually, this probably shouldn't be ignored if the
                # entire remove block was comments
                context['ignore_next_add'] = True
            elif line.startswith("+"):
                if not context['ignore_next_add']:
                    if not re_c_file_comment.match(line[1:]):
                        context['blame_lines'].append((context['line_number'], False))
                        context['ignore_next_add'] = True
            else:
                context['line_number'] += 1
                context['ignore_next_add'] = False
            return context

        def fini(filename, context):
            blame_lines = context['blame_lines']

            # Nothing to blame, so carry on (my wayward son)
            if len(blame_lines) == 0:
                return

            previous_rev = previous_revision(git_commit.hexsha)
            # If the blame doesn't work, it's because the file doesn't exist in the
            # currently checked out branch, so switch the branch to the revision of
            # the blame
            try:
                blame = self.git.blame(["-l", "-s", "-w", "--root", previous_rev, filename]).replace('\r','').splitlines()
            except:
                self.switch_to_revision(previous_rev)
                blame = self.git.blame(["-l", "-s", "-w", "--root", previous_rev, filename]).replace('\r','').splitlines()

            # TODO: The blame also includes the file location if it was different
            #       before, we could take this into account. Currently the file
            #       stored in the database is the most recent name, which is
            #       arguably better, but less correct
            for line, add_removal in blame_lines:
                # The line is 1-indexed since it is a line number, and the blame is
                # 0-indexed, so adjust
                introducing_sha1 = blame[line-1].split()[0]

                # Get the database representation of this commit (which is introducing)
                git_commit_introducing = self.git_repository.commit(introducing_sha1)
                db_commit_introducing = get_or_create_db_commit(git_commit_introducing)

                # Create the introducing commit
                db_introducing_commit = models.IntroducingCommit.objects.get_or_create(commit=db_commit_introducing, fixing_commit=db_fixing_commit)[0]
                
                if add_removal:
                    # Get the file representation in the database
                    lock_file.acquire()
                    db_file = models.File.objects.get_or_create(repository=db_repository, name=filename)[0]
                    lock_file.release()

                    try:
                        db_removal = models.IntroducingCommitFileRemoval.objects.get(introducing_commit=db_introducing_commit, file=db_file)
                    except models.IntroducingCommitFileRemoval.DoesNotExist:
                        db_removal = models.IntroducingCommitFileRemoval.objects.create(introducing_commit=db_introducing_commit, file=db_file, lines_code=0)
                    db_removal.lines_code += 1
                    db_removal.save()
                

        # Do the unified diff
        unified_diff(git_commit, init, update, fini, continue_check)

    def run(self):
        self.log("Starting.")
        while True:
            # The commits lock just protects the shared commit iterator
            lock_iter_commits.acquire()
            try:
                commit_sha1 = iter_commits.next().hexsha
            except StopIteration:
                break
            finally:
                lock_iter_commits.release()
            git_commit = self.git_repository.commit(commit_sha1)
            self.analyze(git_commit)

        # Clean-up
        self.log("Cleaning up.")
        self.git.checkout(["master"])
        self.git.branch(["-D", self._current_branch])
        self.log("Finished.")


def merge_rawauthors():
    # Email regular expression modified from django.core.validators.email_re
    email_re = re.compile(
        r"([-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"
        r'|"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\'
        r'[\001-011\013\014\016-\177])*")'
        r'@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?',
        re.IGNORECASE)

    # Restrict all of the RawAuthor objects to be from the current repository
    rawauthor_qs = models.RawAuthor.objects.filter(repository=db_repository)

    # Create an email lookup to a list of RawAuthors
    email_dict = {}
    for rawauthor in rawauthor_qs.exclude(email=''):
        if rawauthor.email.lower() in email_dict:
            email_dict[rawauthor.email.lower()].append(rawauthor)
        else:
            email_dict[rawauthor.email.lower()] = [rawauthor]

    # Attempt to fix people who put their email in the name field
    for rawauthor in rawauthor_qs.filter(email=''):
        match = email_re.search(rawauthor.name)
        if match:
            email = match.group(0)
            if email.lower() in email_dict:
                email_dict[email.lower()].append(rawauthor)
            else:
                email_dict[email.lower()] = [rawauthor]

    # Create a name lookup to a list of emails
    name_dict = {}
    for rawauthor in rawauthor_qs.all():
        name = rawauthor.name
        if name != "":
            email = rawauthor.email
            if name in name_dict:
                name_dict[name].append(email.lower())
            else:
                name_dict[name] = [email.lower()]

    # Merge the rawauthors in the email dict until there's no more
    # Note: If an rawauthor still has no corresponding author there are 2 cases,
    #       1) they have an email and no name (rawauthors still in email_dict
    #          after the break)
    #       2) they have no email and an unmerged name (the rawauthor was never
    #          in email_dict)
    while len(email_dict) > 0:
        try:
            name_stack = [name_dict.iterkeys().next()]
        # We ran out of names, but there are still some emails unaccounted for
        except StopIteration:
            break
        rawauthors = []
        # Go until we run out of names to merge
        while len(name_stack) > 0:
            name = name_stack.pop()
            if name in name_dict:
                # Get all the emails associated with this name
                for email in name_dict[name]:
                    # Claim the email for this author and remove it from
                    # email_dict
                    if email in email_dict:
                        email_rawauthors = email_dict[email]
                        del email_dict[email]
                        # Add any non-duplicate names to the name_stack
                        for rawauthor in email_rawauthors:
                            if name != rawauthor.name:
                                name_stack.append(rawauthor.name)
                        # Merge the rawauthors
                        rawauthors += email_rawauthors
                del name_dict[name]

        # If we're merging
        if len(rawauthors) > 0:
            # Ensure all the authors are the same
            author = rawauthors[0].author
            for rawauthor in rawauthors[1:]:
                assert author == rawauthor.author

            # They don't have an author, so create one
            if not author:
                rawcommits_qs = \
                    models.Commit.objects.filter(raw_author__in=rawauthors)
                recent_commit = rawcommits_qs.order_by("-utc_time")[0]
                recent_rawauthor = recent_commit.raw_author
                name = recent_rawauthor.name
                email = recent_rawauthor.email
                author, created = models.Author.objects.get_or_create(name=name,email=email)
                for rawauthor in rawauthors:
                    rawauthor.author = author
                    rawauthor.save()

    # QuerySet for unmerged authors
    unmerged_qs = rawauthor_qs.filter(author__isnull=True)

    # Helper function for manual merging of unmerged email to merged name
    def manual_merge_email_to_name(email, name):
        try:
            rawauthor = unmerged_qs.get(email=email)
        except models.RawAuthor.DoesNotExist:
            # We already added the author or it actually doesn't exist, so just
            # return
            return
        merged_rawauthor_qs = rawauthor_qs.filter(name=name)
        if merged_rawauthor_qs.count() > 0:
            author = merged_rawauthor_qs[0].author
            assert author != None
        else:
            author = models.Author.objects.create(name=name,
                                                  email=email)
        rawauthor.author = author
        rawauthor.save()
        log("Manually merged RawAuthor %d" % rawauthor.pk)

    def manual_unmerge_author(name, email):
        author = models.Author.objects.get(name=name, email=email)
        for raw_author in  author.raw_authors.all():
            raw_author.author = None
            raw_author.save()
        author.delete()

    # Manual merging for Linux
    if SLUG == "linux":
        manual_merge_email_to_name("jejb@titanic.il.steeleye.com",
                                   "James Bottomley")
        manual_merge_email_to_name("jketreno@io.(none)", "James Ketrenos")
        manual_merge_email_to_name("greg@echidna.(none)", "Greg Kroah-Hartman")
        manual_merge_email_to_name("felipewd@terra.com.br", "Felipe W Damasio")
        manual_unmerge_author('?', '?')

    # Report unmerged RawAuthors
    for rawauthor in unmerged_qs.all():
        # author = models.Author.objects.create(repository=db_repository,
        #                                       name=rawauthor.name,
        #                                       email=rawauthor.email)
        # rawauthor.author = author
        # rawauthor.save()
        log("Unmerged RawAuthor %d" % rawauthor.pk)

def adjust_timezones():
    tzs = {}
    adjustments = 0

    # Timezone information
    if SLUG == 'postgresql':
        tzs['proff@suburbia.net'] = 'Australia/Melbourne'
        tzs['bryanh@giraffe.netgate.net'] = 'America/Los_Angeles'
        tzs['E.Mergl@bawue.de'] = 'Europe/Berlin'
        tzs['byronn@insightdist.com'] = 'America/New_York'
        tzs['peter@retep.org.uk'] = 'Europe/London'
        tzs['vadim4o@yahoo.com'] = 'America/Los_Angeles'
        tzs['vev@michvhf.com'] = 'America/Detroit'
        tzs['pjw@rhyme.com.au'] = 'Australia/Melbourne'
        tzs['lockhart@fourpalms.org'] = 'America/Los_Angeles'
        tzs['inoue@tpf.co.jp'] = 'Asia/Tokyo'
        tzs['barry@xythos.com'] = 'America/Los_Angeles'
        tzs['davec@fastcrypt.com'] = 'America/Toronto'
        tzs['books@ejurka.com'] = 'America/Los_Angeles'
        tzs['db@zigo.dhs.org'] = 'Europe/London'
        tzs['webmaster@postgresql.org'] = 'UTC'
        tzs['JanWieck@Yahoo.com'] = 'America/New_York'
        tzs['darcy@druid.net'] = 'America/Toronto'
        tzs['stark@mit.edu'] = 'Europe/Dublin'
        tzs['teodor@sigaev.ru'] = 'Europe/Moscow'
        tzs['ishii@postgresql.org'] = 'Asia/Tokyo'
        tzs['scrappy@hub.org'] = 'America/Halifax'
        tzs['mail@joeconway.com'] = 'America/Los_Angeles'
        tzs['simon@2ndQuadrant.com'] = 'Europe/London'
        tzs['itagaki.takahiro@gmail.com'] = 'Asia/Tokyo'
        tzs['meskes@postgresql.org'] = 'Europe/Berlin'
        tzs['alvherre@alvh.no-ip.org'] = 'America/Santiago'
        tzs['andrew@dunslane.net'] = 'America/New_York'
        tzs['tgl@sss.pgh.pa.us'] = 'America/New_York'
        tzs['magnus@hagander.net'] = 'Europe/Stockholm'
        tzs['heikki.linnakangas@iki.fi'] = 'Europe/Helsinki'
        tzs['rhaas@postgresql.org'] = 'America/New_York'
        tzs['peter_e@gmx.net'] = 'Europe/Helsinki'
        tzs['bruce@momjian.us'] = 'America/New_York'

    for c in models.Commit.objects.filter(repository=db_repository):
        # Check if there's possibly no timezone information
        if c.local_time == c.utc_time:
            try:
                # Get the timezone
                tz = timezone(tzs[c.raw_author.author.email])
            except KeyError:
                # Handle the special cases
                if c.raw_author.author.email == 'neilc@samurai.com':
                    if c.utc_time.year <= 2007:
                        tz = timezone('America/Toronto')
                    else:
                        tz = timezone('America/Los_Angeles')
                else:
                    # Reraise the exception
                    raise KeyError

                # Modify and save
                time_utc = c.local_time.replace(tzinfo=utc)
                c.local_time = time_utc.astimezone(tz).replace(tzinfo=None)
                c.save()
                adjustments += 1

    log('%d commits with incorrect timezone information.' % adjustments)

# Global variables
db_repository = models.Repository.objects.get_or_create(slug=SLUG)[0]

if CORE:
    directory = args.directory
    if args.encoding:
        git.Commit.default_encoding = args.encoding

    lock_iter_commits = threading.Lock()
    lock_repository = threading.Lock()
    lock_raw_author = threading.Lock()
    lock_commit = threading.Lock()
    lock_file = threading.Lock()
    lock_log = threading.Lock()

    re_c_file_comment = re.compile(r"^\s*(/\*|\*\s|//)")
    re_c_file = re.compile(r"\.(c|cpp|cc|cp|cxx|c\+\+|h|hpp|hh|hp|hxx|h\+\+)$", re.IGNORECASE)
    re_fixing_commit_message = re.compile(r"fix", re.I)
    re_unified_diff_line_numbers = re.compile(r"@@ -(\d+),\d+ \+(\d+),\d+ @@")

    if VERIFY_ADDITIONS:
        verified_additions = {}

    iter_commits = git.Repo(directory, odbt=git.GitCmdObjectDB).iter_commits("master")

    # Set the last commit to master
    last_git_commit = git.Repo(directory, odbt=git.GitCmdObjectDB).commit("master")
    db_commit = get_or_create_db_commit(last_git_commit)
    db_repository.last_commit = db_commit
    db_repository.save()
    log('Set "last_commit" to %s.' % db_commit.sha1)

    num_threads = multiprocessing.cpu_count()
    threads = [SCCThread(i) for i in xrange(num_threads)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

if MERGE_AUTHORS:
    merge_rawauthors()

if ADJUST_TIMEZONES:
    adjust_timezones()

# Close the log file
if LOG:
    log_file.close()

# def classify_authors():
#     author_qs = models.Author.objects.filter(
#         rawauthors__repository=db_repositorysitory).distinct()

#     first_utc_datetime = db_repositorysitory.first_rawcommit.utc_time
#     last_utc_datetime = db_repositorysitory.last_rawcommit.utc_time

#     for author in author_qs:
#         # Get all their datetimes in a sorted list
#         commit_datetimes = []
#         for rawauthor in author.rawauthors.all():
#             for commit in rawauthor.rawcommits.all():
#                 # Make sure the commit is valid
#                 if commit.utc_time >= first_utc_datetime and \
#                    commit.utc_time <= last_utc_datetime:
#                     # Add the datetime to the list (we're using local time here
#                     # so we can compute whether or not this is their day job)
#                     commit_datetimes.append(commit.local_time)
#         commit_datetimes.sort()

#         # The main classification
#         if len(commit_datetimes) == 1:
#             author.classification = 'S'
#         elif len(commit_datetimes) < 20:
#             author.classification = 'O'
#         else:
#             daily_commits = 0
#             weekly_commits = 0
#             monthly_commits = 0

#             last_datetime = commit_datetimes[0]
#             ignore_before_datetime = last_datetime + timedelta(minutes=30)
#             for dt in commit_datetimes[1:]:
#                 if dt >= ignore_before_datetime:
#                     # Use the delta to see how close the commits are
#                     delta = dt - last_datetime
#                     if delta.days < 7:
#                         daily_commits += 1
#                     elif delta.days < 31:
#                         weekly_commits += 1
#                     else:
#                         monthly_commits += 1

#                     # Update the ignore and the last datetime
#                     ignore_before_datetime = dt + timedelta(minutes=30)
#                     last_datetime = dt

#             # Whatever has the higher count, classify the author as such
#             if daily_commits >= weekly_commits and \
#                daily_commits >= monthly_commits:
#                 author.classification = 'D'
#             elif weekly_commits >= daily_commits and \
#                  weekly_commits >= monthly_commits:
#                 author.classification = 'W'
#             else:
#                 author.classification = 'M'

#             # Check to see if this is their job
#             if author.classification == 'D':
#                 # Count the number of normal work hour commits
#                 day_commits = 0
#                 for dt in commit_datetimes:
#                     if not (dt.weekday == 5 or dt.weekday == 6) and \
#                        (dt.hour >=8 and dt.hour <= 16):
#                         day_commits += 1

#                 # We conclude if >85% of their commits are within normal work
#                 # then this is their day job
#                 if float(day_commits)/float(len(commit_datetimes)) > 0.85:
#                     author.classification = 'J'

#         author.save()

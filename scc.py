from datetime import datetime
from time import sleep
import ConfigParser
import argparse
import codecs
import difflib
import git
import os
import re
import threading
os.environ['DJANGO_SETTINGS_MODULE']='scc_website.settings'
from scc_website.apps.repositories import models

# Command line parser
parser = argparse.ArgumentParser(description='Source Control Correlator')
parser.add_argument("--analysis", action='store_true')
parser.add_argument("--author-info", action='store_true')
parser.add_argument("--commit-info", action='store_true')
parser.add_argument("--config", default="linux.ini")
parser.add_argument("--debug", action='store_true')
parser.add_argument("--init-db", action='store_true')
args = parser.parse_args()

# Config parsing
config = ConfigParser.RawConfigParser()
config.read(args.config)
repository_id = config.getint('repository', 'id')
repository_directory = config.get('repository', 'directory')
if args.analysis:
    fix_re = re.compile(config.get('repository', 'regex'), re.I)

# Variables
django_repository = models.Repository.objects.get(pk=repository_id)
database_lock = threading.Lock()
git_cmd = git.Git(repository_directory)
repository = git.Repo(repository_directory)
repository_lock = threading.Lock()
commit_generator = repository.iter_commits('master')
commit_lock = threading.Lock()
log_file = codecs.open("scc.log", "ab", "utf8")
log_lock = threading.Lock()
if args.analysis:
    temp_branch_num = 1

# Regular expressions
email_re = re.compile(r'[A-Z0-9._%+-]+@([A-Z0-9_%+-]+\.)+'
                      r'(\(NONE\)|[A-Z0-9_%+-]+)', re.IGNORECASE)
line_numbers_re = re.compile(r"@@ -(\d+),\d+ \+(\d+),\d+ @@")
comment_re = re.compile(r"^\s*(/\*|\*|//)")
filetypes_re = re.compile(r"\.(cpp|c|h|hpp)$", re.IGNORECASE)

# Logging function
def log(string):
    log_lock.acquire()
    try:
        log_file.write(
            "[%s] %s\n" % (datetime.now().strftime('%Y/%m/%d %H:%M:%S.%f'),
                           string))
        log_file.flush()
    finally:
        log_lock.release()

def clean_author(name, email):
    # Someone doesn't know how to fill out the email section
    if email is None:
        re_search = email_re.search(name)
        name = u""
        if re_search:
            email = re_search.group(0)
        else:
            email = ""

    # Fix up the name if needed
    if type(name).__name__ == 'str':
        name = unicode(name, 'iso_8859_1')

    # Someone decided to try and be tricky
    email = email.replace(' at ', '@')
    email = email.replace('-at-', '@')
    email = email.replace(' dot ', '.')
    email = email.replace('-dot-', '.')

    # Fixing invalid e-mails
    re_search = email_re.search(email)
    if re_search and (email != re_search.group(0) or re_search.group(0) == ""):
        if args.debug:
            old_email = email
            
        email = re_search.group(0)

        if args.debug:
            log("Author('%s', '%s') changed e-mail from '%s'" % (name, email, old_email))
    elif not re_search and email != "":
        if args.debug:
            old_email = email

        email = email.lower()
        email = email.replace(' ', '-')
        email = "%s@unknown.com" % email
        
        if args.debug:
            log("Author('%s', '%s') changed e-mail from '%s'" % (name, email, old_email))
    return (name[0:75], email[0:75])

def init_author(name, email):
    # Need a lock so we don't get 2 entries with the same e-mail
    database_lock.acquire()
    try:
        try:
            author = models.Author.objects.get(repository=django_repository, email=email)
            if args.debug and author.name != name:
                log("Author('%s', '%s') ignoring name '%s'" % (author.name, email, name))
        except:
            author = models.Author.objects.create(repository=django_repository, name=name, email=email)
    finally:
        database_lock.release()
    return author

def init_commit(author, sha1, utc_time, local_time):
    try:
        models.Commit.objects.get(author=author, sha1=sha1)
    except:
        models.Commit.objects.create(author=author, sha1=sha1, utc_time=utc_time, local_time=local_time)

def get_author(email):
    return models.Author.objects.get(repository=django_repository, email=email)

class SCCThread(threading.Thread):

    def run(self):
        global temp_branch_num
        while True:
            # Get the next commit if available, stop otherwise
            commit_lock.acquire()
            try:
                commit = commit_generator.next()
                name = commit.author.name
                email = commit.author.email
                sha1 = commit.hexsha
                if args.init_db:
                    gmt_time = datetime.utcfromtimestamp(commit.authored_date)
                    local_time = datetime.utcfromtimestamp(commit.authored_date-commit.author_tz_offset)
                if args.analysis:
                    diffs = []
                    if not len(commit.parents) > 1 and fix_re.search(commit.message):
                        try:
                            diff_index = commit.diff("%s~1" % commit.hexsha)
                        # An exception occurs if this commit does not have any previous commits
                        except:
                            diff_index = []
                            
                        for diff in diff_index:
                            # Set the blobs
                            current_blob = diff.a_blob
                            previous_blob = diff.b_blob

                            # End early
                            if ((previous_blob is None) or (current_blob is None)):
                                continue

                            # Set the files
                            current_file = current_blob.path
                            previous_file = previous_blob.path

                            # Ignore files which are not .c, .h or .cpp
                            if not (filetypes_re.search(previous_file) and filetypes_re.search(current_file)):
                                continue

                            # Read the data and get the lines
                            current_lines = current_blob.data_stream.read().splitlines()
                            previous_lines = previous_blob.data_stream.read().splitlines()

                            diffs.append((previous_file, previous_lines, current_file, current_lines))
                if args.commit_info:
                    diffs = []
                    try:
                        diff_index = commit.diff("%s~1" % commit.hexsha)
                    # An exception occurs if this commit does not have any previous commits
                    except:
                        diff_index = []

                    for diff in diff_index:
                        # Set the blobs
                        current_blob = diff.a_blob
                        previous_blob = diff.b_blob

                        # End early
                        if ((previous_blob is None) or (current_blob is None)):
                            continue

                        # Set the files
                        current_file = current_blob.path
                        previous_file = previous_blob.path

                        # Ignore files which are not .c, .h or .cpp
                        if not (filetypes_re.search(previous_file) and filetypes_re.search(current_file)):
                            continue

                        # Read the data and get the lines
                        current_lines = current_blob.data_stream.read().splitlines()
                        previous_lines = previous_blob.data_stream.read().splitlines()

                        diffs.append((previous_file, previous_lines, current_file, current_lines))
            except StopIteration:
                break
            finally:
                commit_lock.release()
                
            (name, email) = clean_author(name, email)
            if args.init_db:
                author = init_author(name, email)
                init_commit(author, sha1, gmt_time, local_time)

            if args.commit_info:
                this_commit = models.Commit.objects.get(author__repository=django_repository, sha1=sha1)
                
                try:
                    models.CommitInformation.objects.get(commit=this_commit)
                except:
                    introduction_count = this_commit.introductions.count()
                    lines_removed = 0
                    lines_added = 0
                    lines_modified = 0

                    for diff in diffs:
                        (previous_file, previous_lines, current_file, current_lines) = diff

                        # Variables for the diff
                        added_blocks = []
                        removed_blocks = []
                        modified_blocks = []

                        # Compute the diff
                        active = False
                        in_removed_block = False
                        in_added_block = False
                        in_modified_block = False
                        comment_block = False
                        for line in difflib.unified_diff(previous_lines, current_lines):
                            if line.startswith("@@"):
                                active = True

                            if active:
                                if line.startswith("@@"):
                                    m = line_numbers_re.match(line)
                                    previous_line_number = int(m.group(1)) - 1
                                    current_line_number = int(m.group(2)) - 1
                                elif line.startswith("-"):                            
                                    # End added block
                                    if in_added_block:
                                        in_added_block = False
                                        if(in_modified_block):
                                            in_modified_block = False
                                            if not comment_block:
                                                modified_blocks.append((removed_blocks.pop(),(start_line_number, current_line_number)))
                                            else:
                                                removed_blocks.pop()
                                        else:
                                            if not comment_block:
                                                added_blocks.append((start_line_number, current_line_number))
                                        comment_block = False

                                    # Comment check
                                    if comment_block:
                                        if not comment_re.match(line[1:]):
                                            comment_block = False

                                    previous_line_number += 1

                                    # Start new removed block
                                    if not in_removed_block:
                                        in_removed_block = True
                                        start_line_number = previous_line_number
                                        # Check if it's also a block of comments
                                        if comment_re.match(line[1:]):
                                            comment_block = True

                                elif line.startswith("+"):
                                    # End removed block (this is a modified block)
                                    if in_removed_block:
                                        in_removed_block = False
                                        in_modified_block = True
                                        removed_blocks.append((start_line_number, previous_line_number))

                                    # Comment check
                                    if comment_block:
                                        if not comment_re.match(line[1:]):
                                            comment_block = False

                                    current_line_number += 1

                                    # Start new added block
                                    if not in_added_block:
                                        in_added_block = True
                                        start_line_number = current_line_number
                                        # Check if it's also a block of comments
                                        if comment_re.match(line[1:]):
                                            comment_block = True
                                        else:
                                            comment_block = False
                                else:
                                    # End removed block
                                    if in_removed_block:
                                        in_removed_block = False
                                        if not comment_block:
                                            removed_blocks.append((start_line_number, previous_line_number))
                                        comment_block = False

                                    # End added block
                                    if in_added_block:
                                        in_added_block = False
                                        if(in_modified_block):
                                            in_modified_block = False
                                            if not comment_block:
                                                modified_blocks.append((removed_blocks.pop(),(start_line_number, current_line_number)))
                                            else:
                                                removed_blocks.pop()
                                        else:
                                            if not comment_block:
                                                added_blocks.append((start_line_number, current_line_number))

                                        comment_block = False

                                    previous_line_number += 1
                                    current_line_number += 1


                        for block in removed_blocks:
                            lines_removed += (block[1] - block[0] + 1)
                        for block in added_blocks:
                            lines_added += (block[1] - block[0] + 1)
                        for block in modified_blocks:
                            lines_modified += (block[1][1] - block[1][0] + 1)

                    #print introduction_count
                    lines_changed = lines_removed + lines_added + lines_modified
                    models.CommitInformation.objects.create(commit=this_commit, lines_changed=lines_changed, lines_removed=lines_removed, lines_added=lines_added, lines_modified=lines_modified, introduction_count=introduction_count)
                

            if args.analysis and len(diffs) > 0:
                fix_commit = models.Commit.objects.get(author__repository=django_repository, sha1=sha1)
                try:
                    bug = models.Bug.objects.get(fix_commits=fix_commit)
                except:
                    bug = models.Bug.objects.create()
                    bug.fix_commits.add(fix_commit)

                for diff in diffs:
                    (previous_file, previous_lines, current_file, current_lines) = diff

                    # Variables for the diff
                    added_blocks = []
                    removed_blocks = []
                    modified_blocks = []

                    # Compute the diff
                    active = False
                    in_removed_block = False
                    in_added_block = False
                    in_modified_block = False
                    comment_block = False
                    for line in difflib.unified_diff(previous_lines, current_lines):
                        if line.startswith("@@"):
                            active = True

                        if active:
                            if line.startswith("@@"):
                                m = line_numbers_re.match(line)
                                previous_line_number = int(m.group(1)) - 1
                                current_line_number = int(m.group(2)) - 1
                            elif line.startswith("-"):                            
                                # End added block
                                if in_added_block:
                                    in_added_block = False
                                    if(in_modified_block):
                                        in_modified_block = False
                                        if not comment_block:
                                            modified_blocks.append((removed_blocks.pop(),(start_line_number, current_line_number)))
                                        else:
                                            removed_blocks.pop()
                                    else:
                                        if not comment_block:
                                            added_blocks.append((start_line_number, current_line_number))
                                    comment_block = False

                                # Comment check
                                if comment_block:
                                    if not comment_re.match(line[1:]):
                                        comment_block = False

                                previous_line_number += 1

                                # Start new removed block
                                if not in_removed_block:
                                    in_removed_block = True
                                    start_line_number = previous_line_number
                                    # Check if it's also a block of comments
                                    if comment_re.match(line[1:]):
                                        comment_block = True

                            elif line.startswith("+"):
                                # End removed block (this is a modified block)
                                if in_removed_block:
                                    in_removed_block = False
                                    in_modified_block = True
                                    removed_blocks.append((start_line_number, previous_line_number))

                                # Comment check
                                if comment_block:
                                    if not comment_re.match(line[1:]):
                                        comment_block = False

                                current_line_number += 1

                                # Start new added block
                                if not in_added_block:
                                    in_added_block = True
                                    start_line_number = current_line_number
                                    # Check if it's also a block of comments
                                    if comment_re.match(line[1:]):
                                        comment_block = True
                                    else:
                                        comment_block = False
                            else:
                                # End removed block
                                if in_removed_block:
                                    in_removed_block = False
                                    if not comment_block:
                                        removed_blocks.append((start_line_number, previous_line_number))
                                    comment_block = False

                                # End added block
                                if in_added_block:
                                    in_added_block = False
                                    if(in_modified_block):
                                        in_modified_block = False
                                        if not comment_block:
                                            modified_blocks.append((removed_blocks.pop(),(start_line_number, current_line_number)))
                                        else:
                                            removed_blocks.pop()
                                    else:
                                        if not comment_block:
                                            added_blocks.append((start_line_number, current_line_number))

                                    comment_block = False

                                previous_line_number += 1
                                current_line_number += 1

                    # Done looking at the diff; added_blocks, removed_blocks and modified_blocks are valid

                    # Do the blaming
                    commit_lock.acquire()
                    try:
                        if (len(removed_blocks) + len(modified_blocks)) > 0:
                            try:
                                previous_blame = git_cmd.blame(["-l", "-s", "-w", "--root", "%s~1" % sha1, previous_file]).splitlines()
                            except:
                                git_cmd.checkout(["-b", "scc_temp_%d" % temp_branch_num, "%s~1" % sha1])
                                temp_branch_num += 1
                                previous_blame = git_cmd.blame(["-l", "-s", "-w", "--root", "%s~1" % sha1, previous_file]).splitlines()
                        if len(added_blocks) > 0:
                            try:
                                current_blame = git_cmd.blame(["-l", "-s", "-w", "--root", sha1, current_file]).splitlines()
                            except:
                                git_cmd.checkout(["-b", "scc_temp_%d" % temp_branch_num, sha1])
                                temp_branch_num += 1
                                current_blame = git_cmd.blame(["-l", "-s", "-w", "--root", sha1, current_file]).splitlines()
                    finally:
                        commit_lock.release()

                    # Dictionary for bug introduction points
                    introduction = {}

                    for block in added_blocks:
                        # Look at the commit before the block
                        # Reminder: the commit after is at index block[1]
                        sha = current_blame[block[0]-2].split()[0]
                        if sha in introduction:
                            introduction[sha] += 1
                        else:
                            introduction[sha] = 1

                    for block in removed_blocks:
                        for i in xrange(block[0], block[1]+1):
                            sha = previous_blame[i-1].split()[0]
                            if sha in introduction:
                                introduction[sha] += 1
                            else:
                                introduction[sha] = 1

                    for block in modified_blocks:
                        removed_block = block[0]
                        for i in xrange(removed_block[0], removed_block[1]+1):
                            sha = previous_blame[i-1].split()[0]
                            if sha in introduction:
                                introduction[sha] += 1
                            else:
                                introduction[sha] = 1

                    # if VERBOSE_DEBUG:
                    #     print "Listing introduction points"
                    #     for (commit_sha1,num) in introduction.iteritems():
                    #         print commit_sha1, num

                    for (commit_sha1,num) in introduction.iteritems():
                        introduction_commit = models.Commit.objects.get(author__repository=django_repository, sha1=commit_sha1)
                        bug.introduction_commits.add(introduction_commit)
                            
                            # intro_commit = repo.commit(commit_sha1)
                            # # Again, check that the email is not None
                            # intro_commit_email = intro_commit.author.email
                            # if not intro_commit_email:
                            #     intro_commit_email = ""
                            # django_author = models.Author.objects.get_or_create(repository=django_repo, name=intro_commit.author.name, email=intro_commit_email)[0]
                            # django_commit = models.Commit.objects.get_or_create(author=django_author, sha1=commit_sha1, utc_time=datetime.utcfromtimestamp(intro_commit.authored_date), local_time=datetime.utcfromtimestamp(intro_commit.authored_date-commit.author_tz_offset))[0]
                            # django_introduction.commits.add(django_commit)
            if args.author_info:
                author = models.Commit.objects.get(author__repository=django_repository, sha1=sha1).author
                
                

# Spawn the threads, wait, and clean-up
if args.init_db or args.analysis or args.commit_info:
    threads = []
    for x in xrange(8):
        SCCThread().start()
    while not threading.active_count() == 1:
        sleep(1)

# Clean up
if args.analysis:
    try:
        i = 1
        while(True):
            git_cmd.branch(["-D", "scc_temp_%d" % i])
            i += 1
    except:
        pass


if args.author_info:
    for author in models.Author.objects.filter(repository=django_repository):
        dates = []
        for commit in author.commit_set.all():
            dates.append(commit.local_time)
        dates.sort()

        classification = ''
        months_of_experience = 0
        day_job = False

        if len(dates) == 1:
            classification = 'S'
        else:
            daily_commits = 0
            weekly_commits = 0
            monthly_commits = 0
            last_date = dates[0]
            for date in dates[1:]:
                delta = date - last_date
                if delta.days == 0 and delta.seconds < 1800:
                    pass
                elif delta.days < 7:
                    daily_commits += 1
                elif delta.days < 31:
                    weekly_commits += 1
                else:
                    monthly_commits += 1
                last_date = date

            months_of_experience = (dates[-1] - dates[0]).days/30
            if daily_commits >= weekly_commits:
                if daily_commits >= monthly_commits:
                    classification = 'D'
                else:
                    classification = 'M'
            else:
                if weekly_commits >= monthly_commits:
                    classification = 'W'
                else:
                    classification = 'M'
            
            # Day job check
            if classification == "D":
                day_commits = 0
                for date in dates:
                    if not (date.weekday == 5 or date.weekday == 6) and (date.hour >=8 and date.hour <= 16):
                        day_commits += 1

                if float(day_commits)/float(len(dates)) > 0.85:
                    day_job = True

        try:
            models.AuthorInformation.objects.get(author=author)
        except:
            models.AuthorInformation.objects.create(author=author, classification=classification, day_job=day_job, experience=months_of_experience)

log_file.close()

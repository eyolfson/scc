import argparse, git, random, re, ConfigParser

# Command line parser
parser = argparse.ArgumentParser(description='Source Control Correlator')
parser.add_argument("--config", default="postgres.ini")
args = parser.parse_args()

# Config parsing
config = ConfigParser.RawConfigParser()
config.read(args.config)
repository_id = config.getint('repository', 'id')
repository = git.Repo(config.get('repository', 'directory'))
fix_re = re.compile(config.get('repository', 'regex'), re.I)

if args.config == "postgres.ini":
    exclude_sha1 = 'd31084e9d1118b25fd16580d9d8c2924b5740df'
elif args.config == "linux.ini":
    exclude_sha1 = '1da177e4c3f41524e886b7f1b8a0c1fc7321cac2'

# fix_commits = []
# non_fix_commits = []
commits = []

for commit in repository.iter_commits('master'):
    if exclude_sha1 != commit.hexsha:
        if len(commit.parents) > 1:
            entry = (commit.hexsha, True, commit.message)
        else:
            entry = (commit.hexsha, False, commit.message)

        # if not entry[1] and fix_re.search(commit.message):
        #     fix_commits.append(entry)
        # else:
        #     non_fix_commits.append(entry)

        if not entry[1] and fix_re.search(commit.message):
            commits.append((entry, True))
        else:
            commits.append((entry, False))

# output = open('random-sample.txt', 'wb')
# output.write('=== Fix Commits ===\n')
# for entry in random.sample(fix_commits, 100):
#     output.write('Commit: %s\n' % entry[0])
#     output.write('Message:\n%s' % entry[2])
#     output.write('Comment:\n\n')
# output.write('=== Non-Fix Commits ===\n')
# for entry in random.sample(non_fix_commits, 50):
#     output.write('Commit: %s\n' % entry[0])
#     output.write('Merge: %s\n' % entry[1])
#     output.write('Message:\n%s' % entry[2])
#     output.write('Comment:\n\n')
# output.close()

fix_commits = []
non_fix_commits = []
for entry in random.sample(commits, 200):
    if entry[1] == True:
        fix_commits.append(entry[0])
    else:
        non_fix_commits.append(entry[0])

output = open('random-sample.txt', 'wb')
output.write('=== Fix Commits (%d) ===\n' % len(fix_commits))
for entry in fix_commits:
    output.write('Commit: %s\n' % entry[0])
    output.write('Message:\n%s' % entry[2])
    output.write('Comment:\n\n')
output.write('=== Non-Fix Commits (%d) ===\n' % len(non_fix_commits))
for entry in non_fix_commits:
    output.write('Commit: %s\n' % entry[0])
    output.write('Merge: %s\n' % entry[1])
    output.write('Message:\n%s' % entry[2])
    output.write('Comment:\n\n')
output.close()

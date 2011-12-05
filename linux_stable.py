import codecs, difflib, git, os, sys

# Set the path
path = '/home/jon/git/scc-web'
if path not in sys.path:
    sys.path.append(path)
path = '/home/jon/git/scc-web/scc_website'
if path not in sys.path:
    sys.path.append(path)
del path

# Import the Django models
os.environ['DJANGO_SETTINGS_MODULE'] = 'scc_website.settings'
from scc_website.scc.models import *

git.Commit.default_encoding = 'iso-8859-2'

fs_stable_dir = '/home/jon/workspace/linux-stable'
fs_log_dir = 'linux_stable_log'
seperator = '*' * 80
db_repository = Repository.objects.get(slug='linux')

# if not os.path.exists(fs_log_dir):
#     os.mkdir(fs_log_dir)

# git_master_repo = git.Repo('/home/jon/workspace/linux', odbt=git.GitCmdObjectDB)
# git_stable_repo = git.Repo(fs_stable_dir, odbt=git.GitCmdObjectDB)
# git_stable_cmd = git.Git(fs_stable_dir)

# tags = {}
# def add_tag(x):
#     try:
#         tags[x.commit.hexsha] = str(x)
#     except:
#         pass
# map(add_tag, git_stable_repo.tags)

# master_commit_metadata = []
# for c in git_master_repo.iter_commits('master'):
#     if len(c.message) != 0:
#         master_commit_metadata.append((c.hexsha, c.summary))

def analyze_stable_commits(minor):
    stable_branch = 'linux-{0}.y'.format(minor)
    db_stable_branch = LinuxStableBranch.objects.get_or_create(name=stable_branch)[0]

    file_summary = codecs.open('linux_stable_log/{0}_summary'.format(stable_branch), 'w', 'utf-8')
    stable_iter_commits = git_stable_repo.iter_commits('v{0}..{1}'.format(minor, stable_branch))
    stable_commits = 0
    for git_stable_commit in stable_iter_commits:
        stable_hexsha = git_stable_commit.hexsha
        if not stable_hexsha in tags:
            stable_commits += 1
            file_summary.write('Stable sha1: {0}\n'.format(stable_hexsha))

            try:
                LinuxStableCommit.objects.get(branch=db_stable_branch, stable_sha1=stable_hexsha)
                file_summary.write('Database entry exists, skipping\n')
                continue
            except LinuxStableCommit.DoesNotExist:
                pass

            stable_summary = git_stable_commit.summary
            if len(stable_summary) == 0:
                file_summary.write('LINUX_STABLE_ERROR: No summary for stable commit\n')
            file_summary.write('Stable summary: {0}\n'.format(stable_summary))

            max_hexsha = None
            max_summary = None
            max_r = 0.0
            for master_hexsha, master_summary in master_commit_metadata:
                r = difflib.SequenceMatcher(None, stable_summary, master_summary).ratio()
                if r > max_r:
                    max_r = r
                    max_hexsha = master_hexsha
                    max_summary = master_summary

            if max_hexsha:
                file_summary.write('Master sha1: {0}\n'.format(max_hexsha))
                file_summary.write('Master summary: {0}\n'.format(max_summary))
                db_commit = Commit.objects.get(repository=db_repository, sha1=max_hexsha)
                LinuxStableCommit.objects.get_or_create(branch=db_stable_branch, stable_sha1=stable_hexsha, master_commit=db_commit)
            else:
                file_summary.write('LINUX_STABLE_ERROR: No matching greater than 0.0 for stable commit\n')
            file_summary.write('{0}\n'.format(seperator))

    file_summary.write('{0} stable commits\n'.format(stable_commits))
    file_summary.close()
    return stable_commits

# for minor in ['2.6.{0}'.format(x) for x in range(13, 40)] + ['3.{0}'.format(x) for x in range(0, 2)]:
#     if analyze_stable_commits(minor) == 0:
#         git_stable_cmd.checkout(['linux-{0}.y'.format(minor)])
#         print analyze_stable_commits(minor)

def manual_modify(minor, stable_sha1, master_sha1):
    stable_branch = 'linux-{0}.y'.format(minor)
    db_stable_branch = LinuxStableBranch.objects.get(name=stable_branch)
    db_stable_commit = LinuxStableCommit.objects.get(branch=db_stable_branch, stable_sha1=stable_sha1)
    db_commit = Commit.objects.get(repository=db_repository, sha1=master_sha1)
    db_stable_commit.master_commit = db_commit
    db_stable_commit.save()

def manual_remove(minor, stable_sha1):
    stable_branch = 'linux-{0}.y'.format(minor)
    db_stable_branch = LinuxStableBranch.objects.get(name=stable_branch)
    for stable_commit in LinuxStableCommit.objects.filter(branch=db_stable_branch, stable_sha1=stable_sha1):
        stable_commit.delete()

def manual_create(minor, stable_sha1, master_sha1):
    stable_branch = 'linux-{0}.y'.format(minor)
    db_stable_branch = LinuxStableBranch.objects.get(name=stable_branch)
    db_commit = Commit.objects.get(repository=db_repository, sha1=master_sha1)
    db_stable_commit = LinuxStableCommit.objects.create(branch=db_stable_branch, stable_sha1=stable_sha1, master_commit=db_commit)

manual_modify('2.6.13', '910573c7c4aced8fd5f45c334cc67862e3424d92', 'abd559b1052e28d8b9c28aabde241f18fa89090b')
manual_modify('2.6.14', '168e438187d99f5c6d73176efb673c0106b44304', '14904398e5b573d13f8c8dbd43a452ff34c0efc2')
manual_modify('2.6.14', '0a63dca5ae2f975e08deae7e6c743a477af04367', 'b7964c3d88668cef57e1a99861477168eeff4743')
manual_remove('2.6.14', '841f70676036b309f7102e2c8024dc68c3946990')
manual_create('2.6.14', '841f70676036b309f7102e2c8024dc68c3946990', 'a8c730e85e80734412f4f73ab28496a0e8b04a7b')
manual_create('2.6.14', '841f70676036b309f7102e2c8024dc68c3946990', 'c9526497cf03ee775c3a6f8ba62335735f98de7a')
manual_remove('2.6.14', '8e58cb47ade0e69f3c953a41b67913c430c67879')
manual_create('2.6.14', '8e58cb47ade0e69f3c953a41b67913c430c67879', 'a8c730e85e80734412f4f73ab28496a0e8b04a7b')
manual_create('2.6.14', '8e58cb47ade0e69f3c953a41b67913c430c67879', 'c9526497cf03ee775c3a6f8ba62335735f98de7a')
manual_remove('2.6.14', '4614b4e56fa82c89e02ad27a7221ee76a0c2ed2c')
manual_modify('2.6.14', '067d66baa9df5b9e6bf7e442fc4ee7140ef3cc74', 'af9c142de94ecf724a18700273bbba390873e072')
manual_modify('2.6.14', 'd8122124872548142e3df57d274444f484f318a2', 'c3348760aaffd268f7e91b2185999025fdc5607f')
manual_remove('2.6.14', 'd47698c7ff2a71160e1095161e841af1ddd9fe8b')
manual_remove('2.6.15', 'b74ed9233e914d8b76216168e475a9df62c28ac2')
manual_remove('2.6.15', '166f00bf649517bb377b23e668b3fd52497f63d0')
manual_modify('2.6.15', '93e3d00a9f0158e522cada1088233fad23247882', '143f412eb4c7cc48b9eb4381f9133b7d36c68075')
manual_remove('2.6.15', '8dcd7c19f2624b7150edd60da336da0bb5291bef')
manual_modify('2.6.15', 'fd01ab8d4018937a01cbc221e7a006bcde24c87f', 'c5e3fbf22ccba0879b174fab7ec0e322b1266c2c')
manual_modify('2.6.15', '32065dc4c027c69cc03431155db36ea27f9f98f5', '4e6a510a74145585f4111d60d1b5fd450d795dd8')
manual_remove('2.6.15', 'a426fa9147f034d5355875ffcb91f0a61e5b393a')
manual_remove('2.6.15', 'ec81e3178071f3747bd1522c959972105584514b')
manual_modify('2.6.15', 'e7a9850f9a29508eb9ba7f43e733b01096bc171d', 'fad3aa1e8e2e4123a19b926fefd91ec63dd56497')
manual_modify('2.6.15', '6eef6ea5bf6794c2d0938ba1c91934229ad9873e', '951069e311a2a931bf7c9d838db860f90bf14c45')
manual_remove('2.6.15', '3edcc7870d12de93ba5ae1ca5b5d9f43886ac0ea')
manual_modify('2.6.15', '1bb571727a8e7311a1854f3b770f282d20466d41', 'b341387225832c392ed83b9f89d15668b033a106')
manual_remove('2.6.15', '5fa8ad644faa114c4190484ac50e15236fc7cdd9')
manual_modify('2.6.15', 'd93f4eb4134d693be834627d31cd7c4aac427911', '9eb3394bf2037120881a8846bc67064f49325366')
manual_remove('2.6.15', '187754cae94a299edaeefeba80ac6d87b22bc940')

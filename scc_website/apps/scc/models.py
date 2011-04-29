from django.db import models

class Repository(models.Model):
    slug = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=50)
    description = models.TextField()
    first_rawcommit = models.OneToOneField("RawCommit", blank=True, null=True, related_name="repository_first")
    last_rawcommit = models.OneToOneField("RawCommit", blank=True, null=True, related_name="repository_last")

    def rawcommit_query_set(self):
        return RawCommit.objects.filter(rawauthor__repository=self)

    def bug_values_query_set(self):
        return Bug.objects.filter(fixing_rawcommit__rawauthor__repository=self).values("fixing_rawcommit")

    def bugsource_values_query_set(self):
        return BugSource.objects.filter(rawcommit__rawauthor__repository=self).values("rawcommit").distinct()

    def __unicode__(self):
        return self.name

    @models.permalink
    def get_absolute_url(self):
        return ("scc:repository_detail", (), {"slug": self.slug})

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "repositories"

class RawAuthor(models.Model):
    repository = models.ForeignKey(Repository, related_name="rawauthors")
    name = models.CharField(max_length=75)
    email = models.CharField(max_length=75)
    author = models.ForeignKey("Author", blank=True, null=True, related_name="rawauthors")

    class Meta:
        unique_together = ("repository", "name", "email")

class Author(models.Model):
    CLASSIFICATION_CHOICES = (
        ('J', "Job"),
        ('D', "Daily"),
        ('W', "Weekly"),
        ('M', "Monthly"),
        ('O', "Other"),
        ('S', "Single"),
    )
    repository = models.ForeignKey(Repository, related_name="authors")
    name = models.CharField(max_length=75, db_index=True)
    email = models.CharField(max_length=75)
    classification = models.CharField(max_length=1, choices=CLASSIFICATION_CHOICES, blank=True, null=True)

    def __unicode__(self):
        return u"%s: %s <%s>" % (self.repository.name, self.name, self.email)

    @models.permalink
    def get_absolute_url(self):
        return ("scc:author_detail", (), {"slug":self.repository.slug, "pk": self.pk})

    def rawcommit_query_set(self):
        return RawCommit.objects.filter(rawauthor__author=self)

    def bug_values_query_set(self):
        return Bug.objects.filter(fixing_rawcommit__rawauthor__author=self).values("fixing_rawcommit")

    def bugsource_values_query_set(self):
        return BugSource.objects.filter(rawcommit__rawauthor__author=self).values("rawcommit").distinct()

    class Meta:
        ordering = ["name"]
        unique_together = ("repository", "name", "email")

class RawCommit(models.Model):
    rawauthor = models.ForeignKey(RawAuthor, related_name="rawcommits")
    sha1 = models.CharField(max_length=40, db_index=True)
    merge = models.BooleanField()
    utc_time = models.DateTimeField()
    local_time = models.DateTimeField()

    def __unicode__(self):
        return u"%s: %s" % (self.rawauthor.repository.name, self.sha1)

    def list_display(self):
        return u"%s... %s [%s]" % (self.sha1[:6], self.rawauthor.author.name, self.utc_time.strftime("%a %I:%M %p"))

    @models.permalink
    def get_absolute_url(self):
        return ("scc:rawcommit_detail", (), {"slug": self.rawauthor.repository.slug, "sha1": self.sha1})

class Commit(models.Model):
    rawcommit = models.OneToOneField(RawCommit, primary_key=True)
    lines_changed_code = models.PositiveIntegerField()
    lines_changed_comments = models.PositiveIntegerField()
    lines_changed_other = models.PositiveIntegerField()

class Bug(models.Model):
    introducing_rawcommits = models.ManyToManyField(RawCommit, related_name="bugs", through="BugSource")
    fixing_rawcommit = models.OneToOneField(RawCommit, primary_key=True, related_name="bug_fix")

class BugSource(models.Model):
    rawcommit = models.ForeignKey(RawCommit, related_name="bugsources")
    bug = models.ForeignKey(Bug, related_name="bugsources")
    files = models.ManyToManyField("File", related_name="bugsources")

class File(models.Model):
    name = models.CharField(max_length=256)

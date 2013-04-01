from django.db import models
from django import template
from django.core.files.storage import FileSystemStorage
from django.conf import settings
import xhtml2pdf.pisa as pisa
import cStringIO as StringIO
from pyPdf import PdfFileReader
import os
import uuid
from synergy.contrib.prospects.printouts.signals import pdf_done


class PDFTemplate(models.Model):
    name = models.SlugField(max_length=255, verbose_name="PDF template machine-name",unique=True)
    verbose_name = models.CharField(max_length=255, verbose_name="Verbose name")
    filename = models.CharField(max_length=255, verbose_name="Filename")
    header = models.TextField(blank=True)
    body = models.TextField(blank=True)
    footer = models.TextField(blank=True)
    parent = models.ForeignKey('self', null=True, blank=True)

    def __unicode__(self):
        return self.name

    def get_template(self):
        return template.Template(self.header + self.body + self.footer)

    def get_context(self):
        return {'images': dict((image.image.name, image.image) for image in self.images.all()) }

    def get_pdf(self,context,variant_pdf):
        local_ctx = context.copy()
        local_ctx.update(self.get_context())
        local_ctx['uuid'] = uuid.uuid4()
        tpl = self.get_template()
        pdf_ctx = self.write_result(tpl,local_ctx)
        # HACK: get number of pages in pdf
        output = PdfFileReader( pdf_ctx.dest )
        local_ctx['pdf_num_pages'] = output.getNumPages()

        pdf_ctx = self.write_result(tpl,local_ctx)
        pdf_done.send(sender=variant_pdf.__class__, instance=variant_pdf, pdf_content=pdf_ctx.dest,  uuid=local_ctx['uuid'])
        return pdf_ctx.dest

    def write_result(self, tpl, context):
        html = tpl.render(template.Context(context))
        pdf_ctx = pisa.pisaDocument(StringIO.StringIO(html.encode("UTF-8")),StringIO.StringIO())
        return pdf_ctx
        

    def get_filename(self, context):
        local_ctx = context.copy()
        local_ctx.update(self.get_context())
        tpl = template.Template(self.filename)
        return tpl.render(template.Context(local_ctx))


class PDFTemplateImage(models.Model):
    template = models.ForeignKey('PDFTemplate', related_name='images')
    image = models.ForeignKey('Image', related_name='templates')

    def __unicode__(self):
        return "%s <- %s" % (self.template.name, self.image.name)

files_location = os.path.join(settings.MEDIA_ROOT,'imagelibrary')
file_system_storage = FileSystemStorage(location=files_location, base_url=settings.MEDIA_URL)

def image_save(instance, filename):
    return  os.path.join("%s" % instance.library.name, '%s-%s' % (uuid.uuid4(),filename) )

class Image(models.Model):
    name = models.SlugField(max_length=255, verbose_name="Image library machine-name",unique=True)
    attachment = models.ImageField(upload_to = image_save, storage = file_system_storage)
    note = models.CharField(max_length=255, verbose_name='Note', blank=True)
    date = models.DateTimeField(auto_now_add=True)
    library = models.ForeignKey('ImageLibrary', related_name='images', verbose_name="Library")

    def __unicode__(self):
        return self.name

class ImageLibrary(models.Model):
    name = models.SlugField(max_length=255, verbose_name="Image library machine-name", unique=True)
    verbose_name = models.CharField(max_length=255, verbose_name="Image library name")

    def __unicode__(self):
        return self.name

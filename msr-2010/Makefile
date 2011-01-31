
default: paper

##############################################################################


paper: *.tex
	pdflatex paper
	bibtex paper
	pdflatex paper
	pdflatex paper
#	pdf2ps paper.pdf paper.ps


##############################################################################
bib: paper.bbl

paper.bbl: *.tex paper.bib
	latex paper
	bibtex paper
	latex paper


##############################################################################
clean:
	rm -f   *.aux \
                *.bbl \
                *.blg \
                *.dvi \
                *.log \
                *.toc \

purge:
	rm -f   *.aux \
                *.bbl \
                *.blg \
                *.dvi \
                *.log \
                *.toc \
                paper.pdf



#!/usr/bin/env python3

import os, sys, time, traceback
import argparse, multiprocessing

# get the path of this script and add it to the "pythonpath"
SCRIPT_PATH = os.path.split(os.path.realpath(os.path.abspath(__file__)))[0]
sys.path.insert(0, SCRIPT_PATH)

from eggnogmapper.emapperException import EmapperException
from eggnogmapper.emapper import Emapper
from eggnogmapper.search.search_modes import SEARCH_MODE_NO_SEARCH, SEARCH_MODE_DIAMOND

from eggnogmapper.common import existing_file, existing_dir, set_data_path, pexists, get_eggnogdb_file, get_eggnog_dmnd_db, get_version, get_citation
from eggnogmapper.vars import LEVEL_NAMES

from eggnogmapper.utils import colorify


__description__ = ('A program for bulk functional annotation of novel '
                    'sequences using EggNOG database orthology assignments')
__author__ = 'Jaime Huerta Cepas'
__license__ = "GPL v2"

def create_arg_parser():
    
    parser = argparse.ArgumentParser()

    ##
    pg_input = parser.add_argument_group('Input Data Options')

    pg_input.add_argument('-i', dest="input", metavar='', type=existing_file,
                    help='Input FASTA file containing query sequences. Required unless -m {SEARCH_MODE_NO_SEARCH}')

    pg_input.add_argument('--translate', action="store_true",
                          help='Assume sequences are CDS instead of proteins')

    pg_input.add_argument('--annotate_hits_table', type=str, metavar='',
                          help='Annotate TSV formatted table with 4 fields:'
                          ' query, hit, evalue, score. Required if -m {SEARCH_MODE_NO_SEARCH} and --no_refine.')
        
    pg_input.add_argument("--data_dir", metavar='', type=existing_dir,
                          help='Path to eggnog-mapper databases.') # DATA_PATH in eggnogmapper.commons
        
    ##
    pg_search = parser.add_argument_group('Search Options')

    pg_search.add_argument('-m', dest='mode',
                           choices = [SEARCH_MODE_DIAMOND, SEARCH_MODE_NO_SEARCH],
                           default=SEARCH_MODE_DIAMOND,
                           help=(
                               f'{SEARCH_MODE_DIAMOND}: search seed orthologs using diamond (-i is required). '
                               f'{SEARCH_MODE_NO_SEARCH}: skip seed orthologs search (--annotate_hits_table is required). '
                               f'Default:{SEARCH_MODE_DIAMOND}'
                           ))

    pg_search.add_argument('--seed_ortholog_evalue', default=0.001, type=float, metavar='',
                           help='Min E-value expected when searching for seed eggNOG ortholog.'
                           ' Queries not having a significant'
                           ' seed orthologs will not be annotated. Default=0.001')

    pg_search.add_argument('--seed_ortholog_score', default=60, type=float, metavar='',
                           help='Min bit score expected when searching for seed eggNOG ortholog.'
                           ' Queries not having a significant'
                           ' seed orthologs will not be annotated. Default=60')
    
    ##
    pg_diamond = parser.add_argument_group('Diamond Search Options')
	
    pg_diamond.add_argument('--dmnd_db',
		    help="Path to DIAMOND-compatible database")

    pg_diamond.add_argument('--matrix', dest='matrix', 
                    choices = ['BLOSUM62', 'BLOSUM90','BLOSUM80','BLOSUM50','BLOSUM45','PAM250','PAM70','PAM30'], 
                    default=None, help='Scoring matrix')

    pg_diamond.add_argument('--gapopen', dest='gapopen', type=int, default=None, 
                    help='Gap open penalty')

    pg_diamond.add_argument('--gapextend', dest='gapextend', type=int, default=None, 
                    help='Gap extend  penalty')

    pg_diamond.add_argument('--query-cover', dest='query_cover', type=float, default=0,
                    help='Report only alignments above the given percentage of query cover. Default=0')

    pg_diamond.add_argument('--subject-cover', dest='subject_cover', type=float, default=0,
                    help='Report only alignments above the given percentage of subject cover. Default=0')
    
    ##
    pg_annot = parser.add_argument_group('Annotation Options')

    pg_annot.add_argument("--no_annot", action="store_true",
                        help="Skip functional annotation, reporting only hits")
    
    pg_annot.add_argument("--tax_scope", type=str, choices=list(LEVEL_NAMES.keys())+["auto"],
                    default='auto', metavar='',
                    help=("Fix the taxonomic scope used for annotation, so only orthologs from a "
                          "particular clade are used for functional transfer. "
                          "By default, this is automatically adjusted for every query sequence."))

    pg_annot.add_argument('--target_orthologs', choices=["one2one", "many2one",
                                                         "one2many","many2many", "all"],
                          default="all",
                          help='defines what type of orthologs should be used for functional transfer')

    pg_annot.add_argument('--excluded_taxa', type=int, metavar='',
                          help='(for debugging and benchmark purposes)')

    pg_annot.add_argument('--go_evidence', type=str, choices=('experimental', 'non-electronic'),
                          default='non-electronic',
                          help='Defines what type of GO terms should be used for annotation:'
                          'experimental = Use only terms inferred from experimental evidence'
                          'non-electronic = Use only non-electronically curated terms')

    ##
    pg_out = parser.add_argument_group('Output options')

    pg_out.add_argument('--output', '-o', type=str, metavar='',
                        help="base name for output files")

    pg_out.add_argument("--output_dir", default=os.getcwd(), type=existing_dir, metavar='',
                        help="Where output files should be written")

    pg_out.add_argument("--scratch_dir", metavar='', type=existing_dir,
                        help='Write output files in a temporary scratch dir, move them to the final'
                        ' output dir when finished. Speed up large computations using network file'
                        ' systems.')
        
    pg_out.add_argument('--override', action="store_true",
                    help="Overwrites output files if they exist.")

    pg_out.add_argument("--temp_dir", default=os.getcwd(), type=existing_dir, metavar='',
                    help="Where temporary files are created. Better if this is a local disk.")

    pg_out.add_argument('--no_file_comments', action="store_true",
                        help="No header lines nor stats are included in the output files")

    pg_out.add_argument("--report_orthologs", action="store_true",
                        help="The list of orthologs used for functional transferred are dumped into a separate file")
    

    





    pg_out.add_argument('--keep_mapping_files', action='store_true',
                        help='Do not delete temporary mapping files used for annotation (i.e. HMMER and'
                        ' DIAMOND search outputs)')

    ##
    pg_predict = parser.add_argument_group('Predict orthologs options')

    pg_predict.add_argument("--predict_ortho", action="store_true", help="The list of predicted orthologs")
        
    pg_predict.add_argument('--target_taxa', type=str,
                          default= "all", nargs="+",
                            help='taxa that will be searched for orthologs')

    pg_predict.add_argument('--predict_output_format', choices=["per_query", "per_species"],
                            default= "per_species", help="Choose the output format among: per_query, per_species .Default = per_species")
    
    ##
    g4 = parser.add_argument_group('Execution options')

    g4.add_argument('--cpu', type=int, default=2, metavar='',
                    help="Number of CPUs to be used. --cpu 0 to run with all available CPUs. Default: 2")
    
    # CPC 2019 Check if --servermode is mutually exclusive with diamond mode
    g4.add_argument("--servermode", action="store_true",
                    help='Loads target database in memory and keeps running in server mode,'
                    ' so another instance of eggnog-mapper can connect to this sever.'
                    ' Auto turns on the --usemem flag')

    g4.add_argument('--usemem', action="store_true",
                    help="""If a local hmmpressed database is provided as target using --db,
                    this flag will allocate the whole database in memory using hmmpgmd.
                    Database will be unloaded after execution.""")
    
    parser.add_argument('--version', action='store_true')
    
    return parser

def parse_args(parser):
    
    args = parser.parse_args()

    if args.version:
        print(get_version())
        sys.exit(0)

    # We need to handle this
    # if args.maxhits == 0: 
    #     args.maxhits = None

    if args.data_dir:
        set_data_path(args.data_dir)

    if not args.no_annot and not pexists(get_eggnogdb_file()):
        print(colorify('Annotation database data/eggnog.db not present. Use download_eggnog_database.py to fetch it', 'red'))
        raise EmapperException()

    # Search modes
    if args.mode == SEARCH_MODE_DIAMOND:
        dmnd_db = args.dmnd_db if args.dmnd_db else get_eggnog_dmnd_db()
        if not pexists(dmnd_db):
            print(colorify('DIAMOND database %s not present. Use download_eggnog_database.py to fetch it' % dmnd_db, 'red'))
            raise EmapperException()

        if args.servermode:
            parser.error('--mode [diamond] and --servermode are mutually exclusive')
        else:
            if not args.input:
                parser.error('An input fasta file is required (-i)')
            
    elif args.mode == SEARCH_MODE_NO_SEARCH:
        if not args.annotate_hits_table:
            parser.error(f'No search mode (-m {SEARCH_MODE_NO_SEARCH}) requires a hits table to annotate (--annotate_hits_table FILE.seed_orthologs)')
        if args.no_annot == True:
            parser.error(f'No search mode (-m {SEARCH_MODE_NO_SEARCH}) is not compatible with --no_annot option)')
            
    else:
        parser.error(f'unrecognized search mode (-m {args.mode})')

    if args.cpu == 0:
        args.cpu = multiprocessing.cpu_count()

    # Output file required unless running in servermode
    if not args.servermode and not args.output:
        parser.error('An output project name is required (-o)')

    # Servermode implies using mem-based databases
    if args.servermode:
        args.usemem = True
        
    # Sets GO evidence bases
    if args.go_evidence == 'experimental':
        args.go_evidence = set(["EXP","IDA","IPI","IMP","IGI","IEP"])
        args.go_excluded = set(["ND", "IEA"])

    elif args.go_evidence == 'non-electronic':
        args.go_evidence = None
        args.go_excluded = set(["ND", "IEA"])
    else:
        raise ValueError('Invalid --go_evidence value')



    return args


if __name__ == "__main__":

    parser = create_arg_parser()
    args = parse_args(parser)

    _total_time = time.time()
    try:
        
        print('# ', get_version())
        print('# emapper.py ', ' '.join(sys.argv[1:]))

        emapper = Emapper(args.output, args.output_dir, args.scratch_dir, args.override)
        emapper.run(args, args.mode, args.input, (not args.no_annot), args.annotate_hits_table, args.predict_ortho)

        print(get_citation([args.mode]))
        print('Total time: %g secs' % (time.time()-_total_time))
        
    except EmapperException as ee:
        print(ee)
        sys.exit(1)
    except Exception:
        traceback.print_exc()
        sys.exit(1)
    else:
        print("FINISHED")
        sys.exit(0)

## END

#!/usr/bin/env python
import os
from itertools import combinations

import click

import numpy
from matplotlib import pyplot

from cogent3 import make_table
from cogent3.maths.stats import chisqprob

from scitrack import CachingLogger

from mutation_motif import util, logo, motif_count, log_lin, spectra_analysis

from mutation_motif.height import get_re_char_heights

__author__ = "Gavin Huttley"
__copyright__ = "Copyright 2016, Gavin Huttley, Yicheng Zhu"
__credits__ = ["Gavin Huttley", "Yicheng Zhu"]
__license__ = "GPL"
__version__ = "0.3"
__maintainer__ = "Gavin Huttley"
__email__ = "Gavin.Huttley@anu.edu.au"
__status__ = "Development"


LOGGER = CachingLogger(create_dir=True)


def format_offset(fig, fontsize):
    """formats the offset text for all axes"""
    for ax in fig.axes:
        t = ax.yaxis.get_offset_text()
        t.set_size(fontsize)


def make_summary(results):
    '''returns records from analyses as list'''
    rows = []
    for position_set in results:
        if type(position_set) != str:
            position = ':'.join(position_set)
        else:
            position = position_set

        re = results[position_set]['rel_entropy']
        dev = results[position_set]['deviance']
        df = results[position_set]['df']
        prob = results[position_set]['prob']
        formula = results[position_set]['formula']
        rows.append([position, re, dev, df, prob, formula])
    return rows


def get_selected_indices(stats, group_label=None, group_ref=None):
    """returns indices for selecting dataframe records for display"""
    if group_label and group_ref is None:  # TODO this logic needs improving
        val = dict(strand='+').get(group_label, '1')
        indices = numpy.logical_and(stats['mut'] == 'M',
                                    stats[group_label] == val)
    elif group_label and group_ref:
        indices = numpy.logical_and(stats['mut'] == 'M',
                                    stats[group_label] == group_ref)
    else:
        indices = stats['mut'] == 'M'
    return indices


def get_grouped_combined_counts(table, position, group_label):
    """wraps motif_count.get_combined_counts for groups"""
    group_cats = table.distinct_values(group_label)
    all_data = []
    header = None
    for category in group_cats:
        subtable = table.filtered(lambda x: x == category, columns=group_label)
        counts = motif_count.get_combined_counts(subtable, position)
        if header is None:
            header = [group_label] + list(counts.header)

        counts = counts.with_new_column(group_label, lambda x: category,
                                        columns=counts.header[0])
        all_data.extend(counts.tolist(header))
    counts = make_table(header=header, rows=all_data)
    counts.sorted(columns=[group_label, 'mut'])
    return counts


def get_position_effects(table, position_sets, group_label=None):
    pos_results = {}
    grouped = group_label is not None
    if grouped:
        assert len(table.distinct_values(group_label)) == 2

    for position_set in position_sets:
        if not grouped:
            counts = motif_count.get_combined_counts(table, position_set)
        else:
            counts = get_grouped_combined_counts(table, position_set,
                                                 group_label=group_label)
        rel_entropy, deviance, df, stats, formula = \
            log_lin.position_effect(counts, group_label=group_label)
        if deviance < 0:
            p = 1.0
        else:
            p = chisqprob(deviance, df)

        pos_results[position_set] = dict(rel_entropy=rel_entropy,
                                         deviance=deviance, df=df, stats=stats,
                                         formula=formula, prob=p)
    return pos_results


def single_position_effects(table, positions, group_label=None):
    single_results = get_position_effects(table, positions,
                                          group_label=group_label)
    return single_results


def get_single_position_fig(single_results, positions, figsize,
                            group_label=None, group_ref=None, figwidth=None,
                            xlabel_fontsize=14, ylabel_fontsize=14,
                            xtick_fontsize=14, ytick_fontsize=14):
    num_pos = len(positions) + 1
    mid = num_pos // 2

    position_re = numpy.zeros((num_pos,), float)
    rets = numpy.zeros((4, num_pos), float)
    characters = [list('ACGT') for i in range(num_pos)]
    for index, pos in enumerate(positions):
        if index >= mid:
            index += 1

        stats = single_results[pos]['stats']
        position_re[index] = single_results[pos]['rel_entropy']
        mut_stats = stats[get_selected_indices(stats, group_label=group_label,
                                               group_ref=group_ref)][['base',
                                                                      'ret']]
        mut_stats = mut_stats.sort_values(by='ret')
        characters[index] = list(mut_stats['base'])
        rets[:, index] = mut_stats['ret']

    heights = get_re_char_heights(rets, re_positionwise=position_re)
    fig = logo.draw_multi_position(heights.T, characters=characters,
                                   position_indices=list(range(num_pos)),
                                   figsize=figsize, figwidth=figwidth,
                                   verbose=False)

    if figwidth:
        fig.set_figwidth(figwidth)

    ax = fig.gca()
    ax.set_xlabel('Position', fontsize=xlabel_fontsize)
    ax.set_ylabel('RE', rotation='vertical', fontsize=ylabel_fontsize)
    ax.tick_params(axis='x', labelsize=xtick_fontsize, pad=xtick_fontsize // 2,
                   length=0)
    ax.tick_params(axis='y', labelsize=ytick_fontsize, pad=ytick_fontsize // 2)
    return fig


def get_resized_array_coordinates2(positions, motifs):
    '''coords for the position combinations for the smaller array used for
    plotting'''
    # to avoid blank rows/columns in the trellis plot, we reduce the array size
    num_pos = len(positions)
    a = numpy.zeros((num_pos, num_pos), object)
    for motif in motifs:
        indices = list(map(positions.index, motif))
        indices.reverse()
        a[indices[0]][indices[1]] = motif

    new = a[(a != 0).any(axis=1)]
    # it's a 2D array now
    new = new[:, (new != 0).any(axis=0)]
    mapping = {}
    for i in range(new.shape[0]):
        for j in range(new.shape[1]):
            if new[i, j] != 0:
                mapping[new[i, j]] = (i, j)
    return mapping


def get_two_position_effects(table, positions, group_label=None):
    two_pos_results = get_position_effects(
        table, list(combinations(positions, 2)), group_label=group_label)
    return two_pos_results


def get_two_position_fig(two_pos_results, positions, figsize,
                         group_label=None, group_ref=None, figwidth=None,
                         xtick_fontsize=14, ytick_fontsize=14):
    position_sets = list(combinations(positions, 2))
    array_coords = get_resized_array_coordinates2(positions, position_sets)
    coords = list(array_coords.values())
    xdim = max(v[0] for v in coords) + 1
    ydim = max(v[1] for v in coords) + 1
    fig, axarr = pyplot.subplots(xdim, ydim, figsize=figsize, sharex=True,
                                 sharey=True)

    for i in range(xdim - 1):
        for j in range(i + 1, ydim):
            ax = axarr[i, j]
            ax.set_frame_on(False)
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)

    rel_entropies = []
    for position_set in position_sets:
        rel_entropies.append(two_pos_results[position_set]['rel_entropy'])
    ylim = logo.est_ylim(rel_entropies)

    num_pos = len(positions) + 1

    mid_pos = num_pos // 2

    position_re = numpy.zeros((num_pos,), float)
    multi_positions = {}
    characters = numpy.zeros((num_pos, 16), str)

    for pair in position_sets:
        rets = numpy.zeros((16, num_pos), float)
        indices = list(map(positions.index, pair))
        row, col = array_coords[pair]
        ax = axarr[row, col]

        # now adjust indices to reflect position along sequence
        for i in range(2):
            if indices[i] >= mid_pos:
                indices[i] += 1

        position_re.put(indices, two_pos_results[pair]['rel_entropy'])

        stats = two_pos_results[pair]['stats']
        mut_stats = stats[get_selected_indices(
            stats, group_label=group_label,
            group_ref=group_ref)][['base1', 'base2', 'ret']]
        mut_stats = mut_stats.sort_values(by='ret')

        characters[indices[0]] = list(mut_stats['base1'])
        characters[indices[1]] = list(mut_stats['base2'])

        for index in indices:
            rets[:, index] = mut_stats['ret']

        heights = get_re_char_heights(rets, re_positionwise=position_re)
        multi_positions[pair] = dict(rets=rets, indices=indices,
                                     characters=characters, heights=heights)
        logo.draw_multi_position(char_heights=heights.T, characters=characters,
                                 position_indices=indices, ax=ax, ylim=ylim,
                                 xtick_fontsize=xtick_fontsize,
                                 ytick_fontsize=ytick_fontsize)
    return fig


def get_resized_array_coordinates3(positions, position_set):
    '''coords for the position combinations for the smaller array used
    for plotting'''
    # to avoid blank rows/columns in the trellis plot, we reduce the array size
    num_pos = len(positions)
    a = numpy.zeros((num_pos, num_pos, num_pos), object)
    for triple in position_set:
        indices = list(map(positions.index, triple))
        indices.reverse()
        a[indices[0]][indices[1]][indices[2]] = triple

    new = a.flatten()
    new = new[new != 0]
    new.sort()
    new = new.reshape((2, 2))
    mapping = {}
    for i in range(new.shape[0]):
        for j in range(new.shape[1]):
            if new[i, j] != 0:
                mapping[new[i, j]] = (i, j)
    return mapping


def get_three_position_effects(table, positions, group_label=None):
    three_pos_results = get_position_effects(table,
                                             list(combinations(positions, 3)),
                                             group_label=group_label)
    return three_pos_results


def get_three_position_fig(three_pos_results, positions, figsize,
                           group_label=None, group_ref=None, figwidth=None,
                           xtick_fontsize=14, ytick_fontsize=14):
    position_sets = list(combinations(positions, 3))
    array_coords = get_resized_array_coordinates3(positions, position_sets)

    coords = list(array_coords.values())
    xdim = max(v[0] for v in coords) + 1
    ydim = max(v[1] for v in coords) + 1

    fig, axarr = pyplot.subplots(xdim, ydim, figsize=figsize, sharex=True,
                                 sharey=True)

    for i in range(xdim):
        for j in range(ydim):
            if (i, j) in coords:
                continue

            ax = axarr[i, j]
            ax.set_frame_on(False)
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)

    num_pos = len(positions) + 1
    mid_pos = num_pos // 2

    rel_entropies = []
    for position_set in position_sets:
        rel_entropies.append(three_pos_results[position_set]['rel_entropy'])
    ylim = logo.est_ylim(rel_entropies)

    position_re = numpy.zeros((num_pos,), float)
    multi_positions = {}
    characters = numpy.zeros((num_pos, 64), str)

    for motif in combinations(positions, 3):
        rets = numpy.zeros((64, num_pos), float)
        indices = list(map(positions.index, motif))
        row, col = array_coords[motif]
        ax = axarr[row, col]

        # now adjust indices to reflect position along sequence
        for i in range(len(indices)):
            if indices[i] >= mid_pos:
                indices[i] += 1

        position_re.put(indices, three_pos_results[motif]['rel_entropy'])

        stats = three_pos_results[motif]['stats']
        mut_stats = stats[
            get_selected_indices(stats, group_label=group_label,
                                 group_ref=group_ref)][['base1', 'base2',
                                                        'base3', 'ret']]
        mut_stats = mut_stats.sort_values(by='ret')

        characters[indices[0]] = list(mut_stats['base1'])
        characters[indices[1]] = list(mut_stats['base2'])
        characters[indices[2]] = list(mut_stats['base3'])

        for index in indices:
            rets[:, index] = mut_stats['ret']

        heights = get_re_char_heights(rets, re_positionwise=position_re)
        multi_positions[motif] = dict(rets=rets, indices=indices,
                                      characters=characters, heights=heights)
        logo.draw_multi_position(char_heights=heights.T, characters=characters,
                                 position_indices=indices, ax=ax, ylim=ylim,
                                 xtick_fontsize=xtick_fontsize,
                                 ytick_fontsize=ytick_fontsize)

    return fig


def get_four_position_effects(table, positions, group_label=None):
    result = get_position_effects(table, list(combinations(positions, 4)),
                                  group_label=group_label)
    return result


def get_four_position_fig(four_pos_results, positions, figsize,
                          group_label=None, group_ref=None, figwidth=None,
                          xtick_fontsize=14, ytick_fontsize=14):
    position_sets = list(combinations(positions, 4))
    assert len(position_sets) == 1
    rel_entropies = [four_pos_results[position_sets[0]]['rel_entropy']]
    ylim = logo.est_ylim(rel_entropies)

    rel_entropy = rel_entropies[0]

    fig = pyplot.figure(figsize=figsize)
    ax = fig.gca()

    num_pos = len(positions) + 1

    mid_pos = num_pos // 2

    position_re = numpy.zeros((num_pos,), float)
    characters = numpy.zeros((num_pos, 256), str)

    rets = numpy.zeros((256, num_pos), float)
    indices = list(range(4))

    # now adjust indices to reflect position along sequence
    for i in range(len(indices)):
        if indices[i] >= mid_pos:
            indices[i] += 1

    position_re.put(indices, rel_entropy)
    stats = four_pos_results[position_sets[0]]['stats']
    mut_stats = stats[
        get_selected_indices(stats, group_label=group_label,
                             group_ref=group_ref)][['base1', 'base2', 'base3',
                                                    'base4', 'ret']]
    mut_stats = mut_stats.sort_values(by='ret')

    characters[indices[0]] = list(mut_stats['base1'])
    characters[indices[1]] = list(mut_stats['base2'])
    characters[indices[2]] = list(mut_stats['base3'])
    characters[indices[3]] = list(mut_stats['base4'])

    for index in indices:
        rets[:, index] = mut_stats['ret']

    heights = get_re_char_heights(rets, re_positionwise=position_re)
    logo.draw_multi_position(char_heights=heights.T, characters=characters,
                             position_indices=indices, ax=ax, ylim=ylim,
                             xtick_fontsize=xtick_fontsize,
                             ytick_fontsize=ytick_fontsize)

    return fig


def single_group(counts_table, outpath, group_label, group_ref, positions,
                 plot_config, first_order, dry_run):
    # Collect statistical analysis results
    summary = []

    max_results = {}
    # Single position analysis
    print("Doing single position analysis")
    single_results = single_position_effects(counts_table, positions,
                                             group_label=group_label)
    summary += make_summary(single_results)

    max_results[1] = max(single_results[p]['rel_entropy']
                         for p in single_results)
    if not dry_run:
        outfilename = os.path.join(outpath, "1.json")
        util.dump_loglin_stats(single_results, outfilename)
        LOGGER.output_file(outfilename, label="analysis1")

    fig = get_single_position_fig(
        single_results, positions,
        plot_config.get('1-way plot', 'figsize'),
        group_label=group_label,
        group_ref=group_ref,
        figwidth=plot_config.get('1-way plot', 'figwidth'),
        xlabel_fontsize=plot_config.get('1-way plot',
                                        'xlabel_fontsize'),
        ylabel_fontsize=plot_config.get('1-way plot',
                                        'ylabel_fontsize'),
        xtick_fontsize=plot_config.get('1-way plot',
                                       'xtick_fontsize'),
        ytick_fontsize=plot_config.get('1-way plot',
                                       'ytick_fontsize'))

    format_offset(fig, int(plot_config.get('1-way plot',
                                           'ytick_fontsize') * .8))
    if not dry_run:
        outfilename = os.path.join(outpath, "1.pdf")
        fig.savefig(outfilename, bbox_inches='tight')
        print("Wrote", outfilename)
        fig.clf()  # refresh for next section

    if first_order:
        msg = "Done! Check %s for your results" % outpath
        summary = make_table(header=['Position', 'RE', 'Deviance', 'df',
                                    'prob', 'formula'],
                            rows=summary, digits=2, space=2)
        if not dry_run:
            outfilename = os.path.join(outpath, "summary.txt")
            summary.write(outfilename, sep='\t')
            LOGGER.output_file(outfilename, label="summary")

        return msg

    print("Doing two positions analysis")
    results = get_two_position_effects(counts_table, positions,
                                       group_label=group_label)
    summary += make_summary(results)

    max_results[2] = max(results[p]['rel_entropy'] for p in results)
    if not dry_run:
        outfilename = os.path.join(outpath, "2.json")
        util.dump_loglin_stats(results, outfilename)
        LOGGER.output_file(outfilename, label="analysis2")

    fig = get_two_position_fig(results, positions,
                               plot_config.get('2-way plot', 'figsize'),
                               group_label=group_label, group_ref=group_ref,
                               xtick_fontsize=plot_config.get(
                                   '2-way plot', 'xtick_fontsize'),
                               ytick_fontsize=plot_config.get('2-way plot', 'ytick_fontsize'))
    fig.set_figwidth(plot_config.get('2-way plot', 'figwidth'))
    x_fsz = plot_config.get('2-way plot', 'xlabel_fontsize')
    y_fsz = plot_config.get('2-way plot', 'ylabel_fontsize')
    fig.text(0.5, plot_config.get('2-way plot', 'xlabel_pad'), 'Position',
             ha='center', va='center', fontsize=x_fsz)
    fig.text(plot_config.get('2-way plot', 'ylabel_pad'), 0.5, 'RE',
             ha='center', va='center', rotation='vertical', fontsize=y_fsz)
    format_offset(fig, int(plot_config.get('2-way plot',
                                           'ytick_fontsize') * .8))
    if not dry_run:
        outfilename = os.path.join(outpath, "2.pdf")
        fig.savefig(outfilename, bbox_inches='tight')
        print("Wrote", outfilename)
        fig.clf()  # refresh for next section

    print("Doing three positions analysis")
    results = get_three_position_effects(counts_table, positions,
                                         group_label=group_label)
    summary += make_summary(results)

    max_results[3] = max(results[p]['rel_entropy'] for p in results)
    if not dry_run:
        outfilename = os.path.join(outpath, "3.json")
        util.dump_loglin_stats(results, outfilename)
        LOGGER.output_file(outfilename, label="analysis3")

    fig = get_three_position_fig(results, positions,
                                 plot_config.get('3-way plot', 'figsize'),
                                 group_label=group_label, group_ref=group_ref,
                                 xtick_fontsize=plot_config.get(
                                     '3-way plot', 'xtick_fontsize'),
                                 ytick_fontsize=plot_config.get('3-way plot', 'ytick_fontsize'))
    fig.set_figwidth(plot_config.get('3-way plot', 'figwidth'))
    x_fsz = plot_config.get('3-way plot', 'xlabel_fontsize')
    y_fsz = plot_config.get('3-way plot', 'ylabel_fontsize')
    fig.text(0.5, plot_config.get('3-way plot', 'xlabel_pad'),
             'Position', ha='center', va='center', fontsize=x_fsz)
    fig.text(plot_config.get('3-way plot', 'ylabel_pad'), 0.5, 'RE',
             ha='center', va='center', rotation='vertical', fontsize=y_fsz)
    format_offset(fig,
                  int(plot_config.get('3-way plot', 'ytick_fontsize') * .8))
    if not dry_run:
        outfilename = os.path.join(outpath, "3.pdf")
        fig.savefig(outfilename, bbox_inches='tight')
        print("Wrote", outfilename)
        fig.clf()  # refresh for next section

    print("Doing four positions analysis")
    results = get_four_position_effects(counts_table, positions,
                                        group_label=group_label)
    summary += make_summary(results)

    max_results[4] = max(results[p]['rel_entropy'] for p in results)
    if not dry_run:
        outfilename = os.path.join(outpath, "4.json")
        util.dump_loglin_stats(results, outfilename)
        LOGGER.output_file(outfilename, label="analysis4")

    fig = get_four_position_fig(results, positions,
                                plot_config.get('4-way plot', 'figsize'),
                                group_label=group_label, group_ref=group_ref)
    fig.set_figwidth(plot_config.get('4-way plot', 'figwidth'))
    ax = fig.gca()
    x_fsz = plot_config.get('4-way plot', 'xlabel_fontsize')
    y_fsz = plot_config.get('4-way plot', 'ylabel_fontsize')
    ax.set_xlabel('Position', fontsize=x_fsz)
    ax.set_ylabel('RE', fontsize=y_fsz)
    format_offset(fig, int(plot_config.get('4-way plot',
                                           'ytick_fontsize') * .8))
    if not dry_run:
        outfilename = os.path.join(outpath, "4.pdf")
        fig.savefig(outfilename, bbox_inches='tight')
        print("Wrote", outfilename)
        fig.clf()  # refresh for next section

    # now generate summary plot
    bar_width = 0.5
    index = numpy.arange(4)
    y_lim = max(max_results.values())
    y_fmt = util.FixedOrderFormatter(numpy.floor(numpy.log10(y_lim)))

    fig = pyplot.figure(figsize=plot_config.get('summary plot', 'figsize'))
    ax = fig.gca()
    ax.yaxis.set_major_formatter(y_fmt)

    bar = pyplot.bar(index, [max_results[i] for i in range(1, 5)], bar_width)
    pyplot.xticks(index + (bar_width / 2.), list(range(1, 5)),
                  fontsize=plot_config.get('summary plot', 'xtick_fontsize'))
    x_sz = plot_config.get('summary plot', 'xlabel_fontsize')
    y_sz = plot_config.get('summary plot', 'ylabel_fontsize')
    ax.set_xlabel("Effect Order", fontsize=x_sz)
    ax.set_ylabel("RE$_{max}$", fontsize=y_sz)

    x_sz = plot_config.get('summary plot', 'xtick_fontsize')
    y_sz = plot_config.get('summary plot', 'ytick_fontsize')
    ax.tick_params(axis='x', labelsize=x_sz, pad=x_sz // 2, length=0)
    ax.tick_params(axis='y', labelsize=y_sz, pad=y_sz // 2)
    format_offset(fig, int(plot_config.get('summary plot',
                                           'ytick_fontsize') * .8))
    if not dry_run:
        outfilename = os.path.join(outpath, "summary.pdf")
        pyplot.savefig(outfilename, bbox_inches='tight')
        print("Wrote", outfilename)

    summary = make_table(header=['Position', 'RE', 'Deviance', 'df',
                                'prob', 'formula'],
                        rows=summary, digits=2, space=2)
    if not dry_run:
        outfilename = os.path.join(outpath, "summary.txt")
        summary.write(outfilename, sep='\t')
        LOGGER.output_file(outfilename, label="summary")

    print(summary)
    pyplot.close('all')
    msg = "Done! Check %s for your results" % outpath
    return msg


_countsfile = click.option('-1', '--countsfile',
                           help='tab delimited file of counts.')
_outpath = click.option('-o', '--outpath',
                        help='Directory path to write data.')
_countsfile2 = click.option('-2', '--countsfile2',
                            help='second group motif counts file.')
_strand_symmetry = click.option('-s', '--strand_symmetry', is_flag=True,
                                help='single counts file but second group is '
                                'strand.')
_force_overwrite = click.option('-F', '--force_overwrite', is_flag=True,
                                help='Overwrite existing files.')
_no_typ3 = util.no_type3_font
_dry_run = click.option('-D', '--dry_run', is_flag=True,
                        help='Do a dry run of the analysis without writing '
                        'output.')
_verbose = click.option('-v', '--verbose', is_flag=True,
                        help='Display more output.')


@click.group()
def main():
    pass


_first_order = click.option('--first_order', is_flag=True,
                            help='Consider only first order effects. Defaults '
                            'to considering up to 4th order interactions.')
_group_label = click.option('-g', '--group_label', help='second group label.')
_group_ref = click.option('-r', '--group_ref', default=None,
                          help='reference group value for results '
                          'presentation.')
_plot_cfg = click.option('--plot_cfg',
                         help='Config file for plot size, font size settings.')
_format = click.option('--format', default='pdf',
                       type=click.Choice(['pdf', 'png']),
                       help='Plot format.')


@main.command()
@_countsfile
@_outpath
@_countsfile2
@_first_order
@_strand_symmetry
@_group_label
@_group_ref
@_plot_cfg
@_no_typ3
@_format
@_verbose
@_dry_run
def nbr(countsfile, outpath, countsfile2, first_order, strand_symmetry,
        group_label, group_ref, plot_cfg, no_type3, format, verbose, dry_run):
    '''log-linear analysis of neighbouring base influence on point mutation

    Writes estimated statistics, figures and a run log to the specified
    directory outpath.

    See documentation for count table format requirements.
    '''
    if no_type3:
        util.exclude_type3_fonts()

    args = locals()

    outpath = util.abspath(outpath)

    if not dry_run:
        util.makedirs(outpath)
        runlog_path = os.path.join(outpath, "analysis.log")
        LOGGER.log_file_path = runlog_path
        LOGGER.log_message(str(args), label='vars')

    counts_filename = util.abspath(countsfile)
    counts_table = util.load_table_from_delimited_file(counts_filename,
                                                       sep='\t')

    LOGGER.input_file(counts_filename, label="countsfile1_path")

    positions = [c for c in counts_table.header if c.startswith('pos')]
    if not first_order and len(positions) != 4:
        raise ValueError("Requires four positions for analysis")

    group_label = group_label or None
    group_ref = group_ref or None
    if strand_symmetry:
        group_label = 'strand'
        group_ref = group_ref or '+'
        if group_label not in counts_table.header:
            print("ERROR: no column named 'strand', exiting.")
            exit(-1)

    if countsfile2:
        print("Performing 2 group analysis")
        group_label = group_label or 'group'
        group_ref = group_ref or '1'
        counts_table1 = counts_table.with_new_column(group_label,
                                                     lambda x: '1',
                                                     columns=counts_table.header[0])

        fn2 = util.abspath(countsfile2)
        counts_table2 = util.load_table_from_delimited_file(fn2, sep='\t')

        LOGGER.input_file(fn2, label="countsfile2_path")

        counts_table2 = counts_table2.with_new_column(group_label,
                                                      lambda x: '2',
                                                      columns=counts_table2.header[0])
        # now combine
        header = [group_label] + counts_table2.header[:-1]
        raw1 = counts_table1.tolist(header)
        raw2 = counts_table2.tolist(header)
        counts_table = make_table(header=header, rows=raw1 + raw2)

        if not dry_run:
            outfile = os.path.join(outpath, 'group_counts_table.txt')
            counts_table.write(outfile, sep='\t')
            LOGGER.output_file(outfile, label="group_counts")

    if dry_run or verbose:
        print()
        print(counts_table)
        print()

    plot_config = util.get_plot_configs(cfg_path=plot_cfg)

    msg = single_group(counts_table, outpath, group_label, group_ref,
                       positions, plot_config, first_order,
                       dry_run)
    print(msg)


@main.command()
@_countsfile
@_outpath
@_countsfile2
@_strand_symmetry
@_force_overwrite
@_no_typ3
@_dry_run
@_verbose
def spectra(countsfile, outpath, countsfile2, strand_symmetry, force_overwrite,
            no_type3, dry_run, verbose):
    '''log-linear analysis of mutation spectra between groups
    '''
    if no_type3:
        util.exclude_type3_fonts()

    spectra_analysis.main(countsfile, outpath,
                          countsfile2, strand_symmetry,
                          force_overwrite, dry_run,
                          verbose)

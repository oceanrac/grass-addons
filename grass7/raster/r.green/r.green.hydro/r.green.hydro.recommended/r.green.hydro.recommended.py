#!/usr/bin/env python
# -- coding: utf-8 --
#
############################################################################
#
# MODULE:      r.green.hydro.recommended
# AUTHOR(S):   Giulia Garegnani
# PURPOSE:     Calculate the optimal position of a plant along a river
#              following user's recommendations
# COPYRIGHT:   (C) 2014 by the GRASS Development Team
#
#              This program is free software under the GNU General Public
#              License (>=v2). Read the file COPYING that comes with GRASS
#              for details.
#
#############################################################################
#

#%module
#% description: Calculate hydropower energy potential with user's recommendations
#% keywords: raster
#%end

##
## REQUIRED INPUTS
##
#%option
#% key: elevation
#% key_desc: name
#% description: Name of elevation raster map [m]
#% required: yes
#%end
#%option G_OPT_V_INPUT
#% key: river
#% label: Name of vector map with interested segments of rivers
#% description: Vector map with the segments of the river that will be analysed
#% required: yes
#%end

##
## OPTIONAL INPUTS
##
#%option
#% key: efficiency
#% type: double
#% key_desc: double
#% description: Efficiency [0-1]
#% required: no
#% options: 0-1
#% answer: 1
#%end
#%option
#% key: len_plant
#% type: double
#% key_desc: double
#% description: Maximum plant length [m]
#% required: no
#% answer: 100
#%end
#%option
#% key: len_min
#% type: double
#% key_desc: double
#% description: Minimum plant length [m]
#% required: no
#% answer: 10
#%end
#%option
#% key: distance
#% type: double
#% key_desc: double
#% description: Minimum distance among plants [m]
#% required: no
#% answer: 0.5
#%end
#%option
#% key: p_min
#% type: double
#% key_desc: double
#% description: Minimum mean power [kW]
#% answer: 10.0
#% required: no
#%end

##
## OPTIONAL INPUTS: LEGAL DISCHARGE
##
#%option
#% key: discharge_current
#% label: Current discharge [m3/s]
#% required: yes
#% guisection: Legal Discharge
#%end
#%option
#% key: mfd
#% label: Minimum Flow Discharge (MFD) [m3/s]
#% required: no
#% guisection: Legal Discharge
#%end
#%option
#% key: discharge_natural
#% label: Natural discharge [m3/s]
#% required: no
#% guisection: Legal Discharge
#%end
#%option
#% key: percentage
#% type: double
#% key_desc: double
#% description: MFD as percentage of natural discharge [%]
#% options: 0-100
#% answer: 20.00
#% required: no
#% guisection: Legal Discharge
#%end

##
## OPTIONAL INPUTS: AREAS TO EXCLUDE
##
#%option G_OPT_V_INPUT
#% key: area
#% label: Areas to exclude
#% description: Vector map with the areas that must be excluded (e.g. Parks)
#% required: no
#% guisection: Areas to exclude
#%end
#%option
#% key: buff
#% type: double
#% key_desc: double
#% description: Buffer for areas to exclude [m]
#% required: no
#% answer: 0
#% guisection: Areas to exclude
#%end
#%option G_OPT_V_INPUT
#% key: points_view
#% label: Vector points of viewing position to exclude
#% description: Vector with the point that are used to compute the visibility
#% required: no
#% guisection: Areas to exclude
#%end
#%option
#% key: visibility_resolution
#% type: double
#% description: Resolution of the visibility map computation
#% required: no
#% answer: 250
#% guisection: Areas to exclude
#%end
#%option
#% key: n_points
#% type: integer
#% description: Number of points for the visibility
#% required: no
#% answer: 0
#% guisection: Areas to exclude
#%end

##
## OUTPUTS
##
#%option G_OPT_V_OUTPUT
#% key: output_plant
#% description: Name of output vector with potential segments
#% required: yes
#%end
#%option G_OPT_V_OUTPUT
#% key: output_point
#% description: Name of output vector with potential intakes and restitution
#% required: no
#%end
#%option G_OPT_V_OUTPUT
#% key: output_vis
#% description: Name of output vector with viewed areas
#% required: no
#% guisection: Areas to exclude
#%end

##
## FLAGS
##
#%flag
#% key: d
#% description: Debug with intermediate maps
#%end
#%flag
#% key: c
#% description: Clean vector lines
#%end

# import system libraries
from __future__ import print_function
import os
import sys
import atexit

# import grass libraries
from grass.script import core as gcore
from grass.pygrass.utils import set_path
from grass.pygrass.messages import get_msgr
from grass.pygrass.vector import VectorTopo
from grass.script import mapcalc

# r.green lib
set_path('r.green', 'libhydro', '..')
set_path('r.green', 'libgreen', os.path.join('..', '..'))
# finally import the module in the library
from libgreen.utils import cleanup

DEBUG = False
TMPRAST = []

if "GISBASE" not in os.environ:
    print("You must be in GRASS GIS to run this program.")
    sys.exit(1)


def set_new_region(new_region):
    gcore.run_command('g.region', res=new_region)
    return


def set_old_region(info):
    gcore.run_command('g.region', rows=info['rows'], e=info['e'],
                      cols=info['cols'], n=info['n'],
                      s=info['s'], w=info['w'], ewres=info['ewres'],
                      nsres=info['nsres'])
    return


def main(opts, flgs):
    TMPRAST, TMPVECT, DEBUG = [], [], False
    atexit.register(cleanup, rast=TMPRAST, vect=TMPVECT, debug=DEBUG)
    OVW = gcore.overwrite()

    dtm = options['elevation']
    river = options['river']  # raster
    discharge_current = options['discharge_current']  # vec
    discharge_natural = options['discharge_natural']  # vec
    mfd = options['mfd']
    len_plant = options['len_plant']
    len_min = options['len_min']
    distance = options['distance']
    output_plant = options['output_plant']
    output_point = options['output_point']
    area = options['area']
    buff = options['buff']
    efficiency = options['efficiency']
    DEBUG = flags['d']
    points_view = options['points_view']
    new_region = options['visibility_resolution']
    final_vis = options['output_vis']
    n_points = options['n_points']
    p_min = options['p_min']
    percentage = options['percentage']
    msgr = get_msgr()

    # set the region
    info = gcore.parse_command('g.region', flags='m')
    if (info['nsres'] == 0) or (info['ewres'] == 0):
        msgr.warning("set region to elevation raster")
        gcore.run_command('g.region', raster=dtm)

    if area:
        if buff:
            gcore.run_command('v.buffer',
                              input=area,
                              output='buff_area',
                              distance=buff, overwrite=OVW)
            area = 'buff_area'
            TMPVECT.append('buff_area')

        gcore.run_command('v.overlay', flags='t',
                          ainput=river,
                          binput=area,
                          operator='not',
                          output='tmp1_river', overwrite=OVW)
        river = 'tmp1_river'
        TMPVECT.append('tmp1_river')

    if points_view:
        info_old = gcore.parse_command('g.region', flags='pg')
        set_new_region(new_region)
        pl, mset = points_view.split('@') if '@' in points_view else (points_view, '')
        vec = VectorTopo(pl, mapset=mset, mode='r')
        vec.open("r")
        string = '0'
        for i, point in enumerate(vec):
            out = 'visual_%i' % i
            gcore.run_command('r.viewshed', input=dtm, output=out,
                              coordinates=point.coords(), overwrite=OVW,
                              memory=1000, flags='b', max_distance=4000,
                              )
            TMPRAST.append(out)
            # we use 4 km sice it the human limit
            string = string + ('+%s' % out)
        #import pdb; pdb.set_trace()

        formula = 'final_vis = %s' % string
        TMPRAST.append('final_vis')
        mapcalc(formula, overwrite=OVW)
        # change to old region
        set_old_region(info_old)
        gcore.run_command('r.to.vect', flags='v', overwrite=OVW,
                          input='final_vis', output='tmp_vis',
                          type='area')
        TMPVECT.append('tmp_vis')
        if int(n_points) > 0:
            where = 'cat<%s' % (n_points)
        else:
            where = 'cat=0'
        gcore.run_command('v.db.droprow', input='tmp_vis',
                          where=where, output=final_vis, overwrite=OVW)
        #TMPVECT.append('final_vis')
        gcore.run_command('v.overlay', flags='t',
                          ainput=river,
                          binput=final_vis,
                          operator='not',
                          output='tmp2_river', overwrite=OVW)
        river = 'tmp2_river'
        TMPVECT.append('tmp2_river')

        #import pdb; pdb.set_trace()

    if mfd:
        formula = 'tmp_discharge=%s-%s' % (discharge_current, mfd)
        mapcalc(formula, overwrite=OVW)
        TMPRAST.append('tmp_discharge')
        discharge_current = 'tmp_discharge'

    elif discharge_natural:
        formula = 'tmp_discharge=%s-%s*%s/100.0' % (discharge_current,
                                                    discharge_natural,
                                                    percentage)
        mapcalc(formula, overwrite=OVW)
        TMPRAST.append('tmp_discharge')
        discharge_current = 'tmp_discharge'

    gcore.run_command('r.green.hydro.optimal',
                      flags='c',
                      discharge=discharge_current,
                      river=river,
                      elevation=dtm,
                      len_plant=len_plant,
                      output_plant=output_plant,
                      output_point=output_point,
                      distance=distance,
                      len_min=len_min,
                      efficiency=efficiency,
                      p_min=p_min)

    print('r.green.hydro.recommended completed!')

if __name__ == "__main__":
    options, flags = gcore.parser()
    sys.exit(main(options, flags))
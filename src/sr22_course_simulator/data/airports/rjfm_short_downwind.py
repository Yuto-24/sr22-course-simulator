"""Task-provided RJFM Short Downwind reference geometry.

The coordinate triples remain in KML order: longitude degrees, latitude
degrees, and absolute altitude metres.  They are canonical transcription data,
not generated aircraft performance.
"""

from __future__ import annotations

from sr22_course_simulator.provenance import SourceCitation


RJFM_SHORT_DOWNWIND_SOURCE = SourceCitation(
    document_title="User-provided RJFM Short Downwind KML",
    extraction_method="verbatim task-provided KML coordinate transcription",
    transformations=(
        "KML longitude,latitude,altitude triples retained without geometric transformation",
    ),
    notes=(
        "the source KML describes the path as 180 degree power-off geometry",
        "the source KML is task-provided and is not represented as an official procedure source",
    ),
)

RJFM_SHORT_DOWNWIND_CIRCLE_SOURCE = SourceCitation(
    document_title="User-provided RJFM Short Downwind Circle KML",
    extraction_method="task-provided KML geometry with requested analytical radius replacement",
    transformations=(
        "original circle tangency point retained",
        "circle radius replaced by ideal coordinated-turn radius at 110 kt and 22 degrees Bank",
        "circle center placed on the RWY09 left normal to preserve tangency with Short Downwind",
    ),
    notes=(
        "circle placement is task-provided and assumption-dependent",
        "circle radius is physics-derived and contains no wind correction or aircraft dynamics",
    ),
)

RJFM_SHORT_DOWNWIND_ENTRY_RWY27_SOURCE = SourceCitation(
    document_title="User-provided RJFM Short Downwind Entry RWY27 KML",
    extraction_method="verbatim task-provided KML coordinate transcription",
    transformations=(
        "KML longitude,latitude,altitude triples retained without geometric transformation",
    ),
    notes=(
        "the source KML identifies a level 1000 ft Short Downwind entry for RWY27",
        "the source KML is task-provided and is not represented as an official procedure source",
    ),
)


RJFM_SHORT_DOWNWIND_COORDINATES = (
    (131.4352955293951, 31.87617923752437, 37.614),
    (131.4334450387508, 31.87604372134293, 59.1493),
    (131.4322831552049, 31.87606588628697, 72.62430000000001),
    (131.4312103206364, 31.87622380006931, 85.2488),
    (131.4302418166674, 31.87651070524524, 97.14190000000001),
    (131.4292009652397, 31.87708252027515, 111.5153),
    (131.4283895142499, 31.87773179869599, 124.4422),
    (131.4277801230632, 31.87840738732327, 136.0616),
    (131.4273585021013, 31.87907020384637, 146.3473),
    (131.4270237422324, 31.8799335299078, 158.7574),
    (131.426898063583, 31.88076737981858, 170.2354),
    (131.4269618902116, 31.88171368832908, 183.1772),
    (131.4271317198729, 31.88252056596611, 194.3686),
    (131.4274569796155, 31.88318326795596, 204.1713),
    (131.4278864419814, 31.88382810153804, 214.286),
    (131.4285022842053, 31.88451393640293, 226.0616),
    (131.4291846893645, 31.8850401725574, 236.7488),
    (131.4298768390489, 31.88544046063843, 246.4577),
    (131.4304783347286, 31.88569273728911, 254.2354),
    (131.4313720741104, 31.88595743655652, 265.2091),
    (131.4323120662455, 31.8860781099208, 276.2306),
    (131.4331425297382, 31.88612970522669, 285.8842),
    (131.4347714082176, 31.88620988314202, 304.8),
    (131.4609733277332, 31.88810532283036, 304.8),
    (131.4642887626693, 31.88839392962839, 270.0906),
    (131.4650352511585, 31.88840894874086, 262.3141),
    (131.4661442926259, 31.88831234837606, 250.7034),
    (131.4671429270224, 31.88802998868875, 239.7417),
    (131.46816140014, 31.88757896983431, 227.7789),
    (131.468933275339, 31.8870589070183, 217.5168),
    (131.4697520316453, 31.88630023639515, 204.8952),
    (131.4703713888397, 31.88535014469554, 191.5757),
    (131.470736961764, 31.88434853632674, 178.7139),
    (131.4708354805836, 31.88338852533817, 166.8942),
    (131.4707283068729, 31.88242927688907, 155.0756),
    (131.4703056569124, 31.88134300989439, 141.0436),
    (131.4697743398839, 31.8804781624168, 129.0791),
    (131.4689761564357, 31.87971333503953, 116.5444),
    (131.4679318343093, 31.87905426421296, 102.9923),
    (131.4669299948615, 31.87863889344767, 91.38030000000001),
    (131.4657370069686, 31.87836407676798, 78.5056),
    (131.4637641443737, 31.8782196695634, 57.8808),
    (131.4626628561745, 31.87815476680839, 46.3827),
    (131.4618402379885, 31.87804843288516, 37.7159),
)


RJFM_SHORT_DOWNWIND_ENTRY_RWY27_COORDINATES = (
    (131.4109320394326, 31.88395134391346, 304.8),
    (131.4109209278805, 31.88417663683572, 304.8),
    (131.4109223032856, 31.88437204440557, 304.8),
    (131.4109645726662, 31.8848758539684, 304.8),
    (131.411057416278, 31.8853624892741, 304.8),
    (131.4111643520542, 31.88570789187308, 304.8),
    (131.4114830649189, 31.88644592245377, 304.8),
    (131.4118516467532, 31.88701616365982, 304.8),
    (131.412527010201, 31.887766112009, 304.8),
    (131.4129744608863, 31.88815477389559, 304.8),
    (131.4135249678382, 31.88851935748959, 304.8),
    (131.4140168137287, 31.88876887534059, 304.8),
    (131.414476793494, 31.8889582151992, 304.8),
    (131.4150967920286, 31.88917144195429, 304.8),
    (131.4156654372266, 31.88929881492, 304.8),
    (131.4162613518207, 31.88938560632862, 304.8),
    (131.4168516916049, 31.88942411364834, 304.8),
    (131.4171919078098, 31.88942095493771, 304.8),
    (131.4173715510524, 31.88941208274275, 304.8),
    (131.417574009997, 31.88940310320874, 304.8),
    (131.4177570713926, 31.88938482708605, 304.8),
    (131.4180814163005, 31.88934403328113, 304.8),
    (131.434277562454, 31.88611382131208, 304.8),
)


# This point is the southern tangency point in the user-provided Circle KML.
# The replacement circle retains this attachment point while its radius is
# recomputed from 110 kt and 22 degrees Bank.
RJFM_SHORT_DOWNWIND_CIRCLE_TANGENCY = (
    131.4475864839089,
    31.887167959162,
    304.8,
)

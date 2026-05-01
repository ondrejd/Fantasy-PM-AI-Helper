import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(const FantasyPmApp());
}

const _positionNames = {
  1: 'Brankář',
  2: 'Obránce',
  3: 'Záložník',
  4: 'Útočník'
};
const _positionShort = {1: 'GK', 2: 'DEF', 3: 'MID', 4: 'FWD'};

String _posName(dynamic pos) =>
    _positionNames[pos is int ? pos : int.tryParse(pos?.toString() ?? '')] ??
    '?';

String _posShort(dynamic pos) =>
    _positionShort[pos is int ? pos : int.tryParse(pos?.toString() ?? '')] ??
    '?';

int? _resolveBadgeCode(
    {String? teamName, String? teamShortName, int? teamFplId}) {
  const nameToBadgeCode = {
    'arsenal': 3,
    'aston villa': 7,
    'avl': 7,
    'bournemouth': 91,
    'bou': 91,
    'brentford': 94,
    'bre': 94,
    'brighton': 36,
    'brighton and hove albion': 36,
    'bha': 36,
    'burnley': 90,
    'bur': 90,
    'chelsea': 8,
    'crystal palace': 31,
    'cry': 31,
    'everton': 11,
    'fulham': 54,
    'ful': 54,
    'ipswich': 40,
    'ipswich town': 40,
    'ips': 40,
    'leicester': 13,
    'leicester city': 13,
    'lei': 13,
    'liverpool': 14,
    'man city': 43,
    'manchester city': 43,
    'mci': 43,
    'man utd': 1,
    'manchester united': 1,
    'mun': 1,
    'newcastle': 4,
    'newcastle united': 4,
    'new': 4,
    "nott'm forest": 17,
    'nottingham forest': 17,
    'nfo': 17,
    'southampton': 20,
    'sou': 20,
    'tottenham': 6,
    'tottenham hotspur': 6,
    'spurs': 6,
    'tot': 6,
    'west ham': 21,
    'west ham united': 21,
    'whu': 21,
    'wolves': 39,
    'wolverhampton': 39,
    'wolverhampton wanderers': 39,
    'wol': 39,
  };

  final byName =
      teamName == null ? null : nameToBadgeCode[teamName.trim().toLowerCase()];
  if (byName != null) {
    return byName;
  }

  final byShort = teamShortName == null
      ? null
      : nameToBadgeCode[teamShortName.trim().toLowerCase()];
  if (byShort != null) {
    return byShort;
  }

  return teamFplId;
}

// Pitch painter
class _PitchPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;
    final paint = Paint()..style = PaintingStyle.fill;
    const stripes = 10;
    for (int i = 0; i < stripes; i++) {
      paint.color =
          (i % 2 == 0) ? const Color(0xFF2E7D32) : const Color(0xFF266428);
      canvas.drawRect(Rect.fromLTWH(0, h / stripes * i, w, h / stripes), paint);
    }
    final rr = RRect.fromRectAndRadius(
        Rect.fromLTWH(0, 0, w, h), const Radius.circular(12));
    canvas.clipRRect(rr);
    final linePaint = Paint()
      ..color = Colors.white.withAlpha(217)
      ..strokeWidth = 1.6
      ..style = PaintingStyle.stroke;
    const pad = 14.0;
    canvas.drawRect(
        Rect.fromLTWH(pad, pad, w - pad * 2, h - pad * 2), linePaint);
    canvas.drawLine(Offset(pad, h / 2), Offset(w - pad, h / 2), linePaint);
    canvas.drawCircle(Offset(w / 2, h / 2), w * 0.18, linePaint);
    canvas.drawCircle(
        Offset(w / 2, h / 2), 3, Paint()..color = Colors.white.withAlpha(217));
    final penW = w * 0.55;
    final penH = h * 0.14;
    canvas.drawRect(Rect.fromLTWH((w - penW) / 2, pad, penW, penH), linePaint);
    canvas.drawRect(
        Rect.fromLTWH((w - penW) / 2, h - pad - penH, penW, penH), linePaint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _JerseyPainter extends CustomPainter {
  final Color primaryColor;
  final Color secondaryColor;

  const _JerseyPainter({
    required this.primaryColor,
    required this.secondaryColor,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final w = size.width;
    final h = size.height;

    final jersey = Path()
      ..moveTo(w * 0.36, h * 0.12)
      ..lineTo(w * 0.20, h * 0.12)
      ..lineTo(w * 0.06, h * 0.28)
      ..lineTo(w * 0.19, h * 0.44)
      ..lineTo(w * 0.29, h * 0.35)
      ..lineTo(w * 0.29, h * 0.90)
      ..lineTo(w * 0.71, h * 0.90)
      ..lineTo(w * 0.71, h * 0.35)
      ..lineTo(w * 0.81, h * 0.44)
      ..lineTo(w * 0.94, h * 0.28)
      ..lineTo(w * 0.80, h * 0.12)
      ..lineTo(w * 0.64, h * 0.12)
      ..lineTo(w * 0.57, h * 0.24)
      ..lineTo(w * 0.43, h * 0.24)
      ..close();

    final fill = Paint()
      ..style = PaintingStyle.fill
      ..color = primaryColor;
    canvas.drawPath(jersey, fill);

    canvas.save();
    canvas.clipPath(jersey);
    if (secondaryColor != primaryColor) {
      final stripe = Paint()
        ..style = PaintingStyle.fill
        ..color = secondaryColor.withAlpha(235);
      canvas.drawRect(
          Rect.fromLTWH(w * 0.42, h * 0.10, w * 0.16, h * 0.84), stripe);
      canvas.drawRect(
          Rect.fromLTWH(w * 0.10, h * 0.54, w * 0.80, h * 0.14), stripe);
    }
    canvas.restore();

    final outline = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..color = Colors.white.withAlpha(220);
    canvas.drawPath(jersey, outline);
  }

  @override
  bool shouldRepaint(covariant _JerseyPainter oldDelegate) {
    return oldDelegate.primaryColor != primaryColor ||
        oldDelegate.secondaryColor != secondaryColor;
  }
}

class FantasyPmApp extends StatelessWidget {
  const FantasyPmApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Fantasy PM Helper',
      theme: ThemeData(colorSchemeSeed: Colors.green, useMaterial3: true),
      home: const HomePage(),
    );
  }
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});
  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  static const Map<String, List<Color>> _clubKitColors = {
    'ars': [Color(0xFFC62828), Color(0xFFF5F5F5)],
    'arsenal': [Color(0xFFC62828), Color(0xFFF5F5F5)],
    'avl': [Color(0xFF7B1E3C), Color(0xFF81D4FA)],
    'aston villa': [Color(0xFF7B1E3C), Color(0xFF81D4FA)],
    'bou': [Color(0xFFD32F2F), Color(0xFF212121)],
    'bournemouth': [Color(0xFFD32F2F), Color(0xFF212121)],
    'bre': [Color(0xFFD32F2F), Color(0xFFF5F5F5)],
    'brentford': [Color(0xFFD32F2F), Color(0xFFF5F5F5)],
    'bha': [Color(0xFF1565C0), Color(0xFFFFFFFF)],
    'brighton': [Color(0xFF1565C0), Color(0xFFFFFFFF)],
    'bur': [Color(0xFF7B1E3C), Color(0xFF64B5F6)],
    'burnley': [Color(0xFF7B1E3C), Color(0xFF64B5F6)],
    'che': [Color(0xFF0D47A1), Color(0xFFE3F2FD)],
    'chelsea': [Color(0xFF0D47A1), Color(0xFFE3F2FD)],
    'cry': [Color(0xFF1565C0), Color(0xFFD32F2F)],
    'crystal palace': [Color(0xFF1565C0), Color(0xFFD32F2F)],
    'eve': [Color(0xFF0D47A1), Color(0xFFE3F2FD)],
    'everton': [Color(0xFF0D47A1), Color(0xFFE3F2FD)],
    'ful': [Color(0xFFF5F5F5), Color(0xFF212121)],
    'fulham': [Color(0xFFF5F5F5), Color(0xFF212121)],
    'ips': [Color(0xFF1565C0), Color(0xFFD32F2F)],
    'ipswich': [Color(0xFF1565C0), Color(0xFFD32F2F)],
    'lei': [Color(0xFF0D47A1), Color(0xFFF5F5F5)],
    'leicester': [Color(0xFF0D47A1), Color(0xFFF5F5F5)],
    'liv': [Color(0xFFC62828), Color(0xFFF5F5F5)],
    'liverpool': [Color(0xFFC62828), Color(0xFFF5F5F5)],
    'mci': [Color(0xFF64B5F6), Color(0xFFFFFFFF)],
    'man city': [Color(0xFF64B5F6), Color(0xFFFFFFFF)],
    'mun': [Color(0xFFC62828), Color(0xFF212121)],
    'man utd': [Color(0xFFC62828), Color(0xFF212121)],
    'new': [Color(0xFF212121), Color(0xFFFFFFFF)],
    'newcastle': [Color(0xFF212121), Color(0xFFFFFFFF)],
    'nfo': [Color(0xFFC62828), Color(0xFFF5F5F5)],
    'nottingham forest': [Color(0xFFC62828), Color(0xFFF5F5F5)],
    'sou': [Color(0xFFD32F2F), Color(0xFFFFFFFF)],
    'southampton': [Color(0xFFD32F2F), Color(0xFFFFFFFF)],
    'tot': [Color(0xFFF5F5F5), Color(0xFF1A237E)],
    'tottenham': [Color(0xFFF5F5F5), Color(0xFF1A237E)],
    'whu': [Color(0xFF7B1E3C), Color(0xFF81D4FA)],
    'west ham': [Color(0xFF7B1E3C), Color(0xFF81D4FA)],
    'wol': [Color(0xFFF9A825), Color(0xFF212121)],
    'wolves': [Color(0xFFF9A825), Color(0xFF212121)],
  };
  final _baseUrlController =
      TextEditingController(text: 'http://127.0.0.1:8000');
  final _fromGwController = TextEditingController();
  final _toGwController = TextEditingController();

  String _status = 'Připraveno';
  Map<String, dynamic>? _currentGw;
  Map<String, dynamic>? _lineup;
  List<dynamic> _projections = const [];
  Map<String, dynamic>? _evaluation;
  Map<String, dynamic>? _evaluationReport;
  Map<String, dynamic>? _health;
  List<dynamic> _fixtures = const [];
  String? _healthError;
  DateTime? _healthCheckedAt;

  int _reportRows = 10;
  int? _reportFromGw;
  int? _reportToGw;
  String _primaryWinnerMetric = 'mae';
  bool _showPitchView = true;

  bool _isUpdating = false;
  bool _isLoadingGw = false;
  bool _isLoadingProjections = false;
  bool _isLoadingLineup = false;
  bool _isEvaluating = false;
  bool _isLoadingReport = false;
  bool _isCheckingHealth = false;
  bool _isLoadingFixtures = false;

  final Set<int> _excludedPlayerIds = {};
  final Set<int> _lockedPlayerIds = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadCurrentGw();
      _loadReport();
      _checkHealth(silent: true);
    });
  }

  @override
  void dispose() {
    _baseUrlController.dispose();
    _fromGwController.dispose();
    _toGwController.dispose();
    super.dispose();
  }

  String get _api => _baseUrlController.text.trim();

  bool get _busy =>
      _isUpdating ||
      _isLoadingGw ||
      _isLoadingProjections ||
      _isLoadingLineup ||
      _isEvaluating ||
      _isLoadingReport ||
      _isCheckingHealth ||
      _isLoadingFixtures;

  Future<void> _checkHealth({bool silent = false}) async {
    if (!silent) {
      setState(() {
        _isCheckingHealth = true;
      });
    } else {
      _isCheckingHealth = true;
    }
    try {
      final resp = await http.get(Uri.parse('$_api/health'));
      if (resp.statusCode >= 400) {
        throw Exception('${resp.statusCode} ${resp.body}');
      }
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      setState(() {
        _health = data;
        _healthError = null;
        _healthCheckedAt = DateTime.now();
      });
    } catch (e) {
      setState(() {
        _health = null;
        _healthError = e.toString();
        _healthCheckedAt = DateTime.now();
      });
    } finally {
      if (mounted) {
        setState(() {
          _isCheckingHealth = false;
        });
      }
    }
  }

  Future<void> _updateData() async {
    setState(() {
      _isUpdating = true;
      _status = 'Aktualizuji data z FPL API...';
    });
    try {
      final resp = await http.post(Uri.parse('$_api/v1/data/update'));
      if (resp.statusCode >= 400) {
        throw Exception('${resp.statusCode} ${resp.body}');
      }
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      setState(() {
        _status =
            'Data aktualizována: týmy ${data['teams']}, hráči ${data['players']}, '
            'kola ${data['gameweeks']}, zápasy ${data['fixtures']}, logy ${data['game_logs']}';
      });
      await _loadCurrentGw();
    } catch (e) {
      setState(() => _status = 'Chyba update-data: $e');
    } finally {
      setState(() => _isUpdating = false);
    }
  }

  Future<void> _loadCurrentGw() async {
    setState(() => _isLoadingGw = true);
    try {
      final resp = await http.get(Uri.parse('$_api/v1/gameweeks/current'));
      if (resp.statusCode == 404) {
        setState(() {
          _currentGw = null;
          _fixtures = const [];
        });
        return;
      }
      if (resp.statusCode >= 400) throw Exception('${resp.statusCode}');
      final gw = jsonDecode(resp.body) as Map<String, dynamic>;
      setState(() => _currentGw = gw);
      await _loadFixturesForCurrentGw();
    } catch (e) {
      setState(() => _status = 'Chyba načítání kola: $e');
    } finally {
      setState(() => _isLoadingGw = false);
    }
  }

  Future<void> _loadFixturesForCurrentGw() async {
    final gw = _currentGw;
    if (gw == null) {
      setState(() => _fixtures = const []);
      return;
    }
    setState(() => _isLoadingFixtures = true);
    try {
      final gwId = gw['gameweek_id'];
      final resp =
          await http.get(Uri.parse('$_api/v1/gameweeks/$gwId/fixtures'));
      if (resp.statusCode == 404) {
        setState(() => _fixtures = const []);
        return;
      }
      if (resp.statusCode >= 400) {
        throw Exception('${resp.statusCode} ${resp.body}');
      }
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      setState(() {
        _fixtures = (data['fixtures'] as List<dynamic>? ?? []);
      });
    } catch (e) {
      setState(() => _status = 'Chyba načítání zápasů: $e');
    } finally {
      if (mounted) {
        setState(() => _isLoadingFixtures = false);
      }
    }
  }

  Future<void> _loadProjections({bool rebuild = false}) async {
    final gw = _currentGw;
    if (gw == null) {
      setState(() => _status = 'Nejdříve načti aktuální kolo.');
      return;
    }
    final gwId = gw['gameweek_id'];
    setState(() {
      _isLoadingProjections = true;
      _status = rebuild ? 'Generuji projekce...' : 'Načítám projekce...';
    });
    try {
      final resp = await http.get(Uri.parse(
          '$_api/v1/gameweeks/$gwId/projections?rebuild=$rebuild&top=100'));
      if (resp.statusCode >= 400) throw Exception('${resp.statusCode}');
      final data = jsonDecode(resp.body) as Map<String, dynamic>;
      setState(() {
        _projections = (data['players'] as List<dynamic>? ?? []);
        _status = 'Projekce načteny (${_projections.length} hráčů)';
      });
    } catch (e) {
      setState(() => _status = 'Chyba projekcí: $e');
    } finally {
      setState(() => _isLoadingProjections = false);
    }
  }

  Future<void> _loadLineup() async {
    final gw = _currentGw;
    if (gw == null) {
      setState(() => _status = 'Nejdříve načti aktuální kolo.');
      return;
    }
    final gwId = gw['gameweek_id'];
    setState(() {
      _isLoadingLineup = true;
      _status = 'Generuji sestavu...';
    });
    try {
      final extraParams = [
        for (final id in _excludedPlayerIds) 'exclude=$id',
        for (final id in _lockedPlayerIds) 'lock=$id',
      ].join('&');
      final uri = Uri.parse(
          '$_api/v1/gameweeks/$gwId/lineup${extraParams.isNotEmpty ? '?$extraParams' : ''}');
      final resp = await http.get(uri);
      if (resp.statusCode >= 400) {
        throw Exception('${resp.statusCode} ${resp.body}');
      }
      setState(() {
        _lineup = jsonDecode(resp.body) as Map<String, dynamic>;
        _status = 'Sestava připravena';
      });
    } catch (e) {
      setState(() => _status = 'Chyba sestavy: $e');
    } finally {
      setState(() => _isLoadingLineup = false);
    }
  }

  Future<void> _evaluate() async {
    final gw = _currentGw;
    if (gw == null) {
      setState(() => _status = 'Nejdříve načti aktuální kolo.');
      return;
    }
    if (gw['finished'] != true) {
      setState(() => _status = 'Kolo ještě není dokončené.');
      return;
    }
    final gwId = gw['gameweek_id'];
    setState(() {
      _isEvaluating = true;
      _status = 'Spouštím evaluaci...';
    });
    try {
      final resp =
          await http.post(Uri.parse('$_api/v1/gameweeks/$gwId/evaluate'));
      if (resp.statusCode >= 400) throw Exception('${resp.statusCode}');
      setState(() {
        _evaluation = jsonDecode(resp.body) as Map<String, dynamic>;
        _status = 'Evaluace dokončena';
      });
      await _loadReport();
    } catch (e) {
      setState(() => _status = 'Chyba evaluace: $e');
    } finally {
      setState(() => _isEvaluating = false);
    }
  }

  Future<void> _loadReport() async {
    setState(() => _isLoadingReport = true);
    try {
      final params = <String, String>{
        'rows': _reportRows.toString(),
        'primary_winner_metric': _primaryWinnerMetric,
      };
      if (_reportFromGw != null) {
        params['from_gameweek'] = _reportFromGw.toString();
      }
      if (_reportToGw != null) params['to_gameweek'] = _reportToGw.toString();
      final uri = Uri.parse('$_api/v1/evaluations/report')
          .replace(queryParameters: params);
      final resp = await http.get(uri);
      if (resp.statusCode >= 400) throw Exception('${resp.statusCode}');
      setState(() =>
          _evaluationReport = jsonDecode(resp.body) as Map<String, dynamic>);
    } catch (_) {
      setState(() => _evaluationReport = null);
    } finally {
      setState(() => _isLoadingReport = false);
    }
  }

  String _fmt(dynamic v, {int digits = 2}) {
    if (v == null) return 'N/A';
    if (v is num) return v.toStringAsFixed(digits);
    return v.toString();
  }

  Color _winnerColor(String? winner, BuildContext context) {
    if (winner == 'baseline') return Colors.orange.shade700;
    if (winner == 'ml') return Colors.blue.shade700;
    return Theme.of(context).colorScheme.onSurfaceVariant;
  }

  Widget _winnerBadge(String? winner, BuildContext context) {
    if (winner == null) return const Text('-', style: TextStyle(fontSize: 12));
    final label = winner == 'baseline'
        ? 'Baseline'
        : winner == 'ml'
            ? 'ML'
            : winner;
    final color = _winnerColor(winner, context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withAlpha(38),
        borderRadius: BorderRadius.circular(99),
        border: Border.all(color: color.withAlpha(128)),
      ),
      child: Text(label,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w700)),
    );
  }

  Widget _sectionCard({required String title, required List<Widget> children}) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          ...children,
        ]),
      ),
    );
  }

  Widget _chip(String label, Color color) {
    return Container(
      margin: const EdgeInsets.only(left: 6),
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
      decoration: BoxDecoration(
        color: color.withAlpha(38),
        borderRadius: BorderRadius.circular(99),
        border: Border.all(color: color.withAlpha(128)),
      ),
      child: Text(label,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w700)),
    );
  }

  String? _teamLogoUrlFromMap(Map<String, dynamic> item) {
    final raw = item['team_logo_url']?.toString();
    if (raw != null && raw.isNotEmpty) {
      return raw;
    }
    final teamFplId = (item['team_fpl_id'] is num)
        ? (item['team_fpl_id'] as num).toInt()
        : null;
    final badgeCode = _resolveBadgeCode(
      teamName: item['team_name']?.toString(),
      teamShortName: item['team_short_name']?.toString(),
      teamFplId: teamFplId,
    );
    if (badgeCode == null) {
      return null;
    }
    return 'https://resources.premierleague.com/premierleague/badges/70/t$badgeCode.png';
  }

  String? _fixtureTeamLogoUrl(Map<String, dynamic> fixture, String side) {
    final key = '${side}_team_logo_url';
    final raw = fixture[key]?.toString();
    if (raw != null && raw.isNotEmpty) {
      return raw;
    }
    final fplIdKey = '${side}_team_fpl_id';
    final teamFplId =
        (fixture[fplIdKey] is num) ? (fixture[fplIdKey] as num).toInt() : null;
    final badgeCode = _resolveBadgeCode(
      teamName: fixture['${side}_team_name']?.toString(),
      teamShortName: fixture['${side}_team_short_name']?.toString(),
      teamFplId: teamFplId,
    );
    if (badgeCode == null) {
      return null;
    }
    return 'https://resources.premierleague.com/premierleague/badges/70/t$badgeCode.png';
  }

  Map<String, int?> _captainAssistantIds(List<dynamic> rawSlots) {
    final slots = rawSlots.cast<Map<String, dynamic>>();
    if (slots.isEmpty) {
      return {'captain': null, 'assistant': null};
    }
    final sorted = [...slots]..sort((a, b) {
        final af = (a['projected_fpts'] as num?)?.toDouble() ?? 0.0;
        final bf = (b['projected_fpts'] as num?)?.toDouble() ?? 0.0;
        return bf.compareTo(af);
      });

    final captain = (sorted.first['player_id'] is num)
        ? (sorted.first['player_id'] as num).toInt()
        : null;

    int? assistant;
    for (final s in sorted.skip(1)) {
      final pid =
          (s['player_id'] is num) ? (s['player_id'] as num).toInt() : null;
      if (pid != null && pid != captain) {
        assistant = pid;
        break;
      }
    }
    return {'captain': captain, 'assistant': assistant};
  }

  Alignment _slotAlignment(String slot) {
    return switch (slot.toUpperCase()) {
      'GK' => const Alignment(0.0, 0.90),
      'DEF1' => const Alignment(-0.70, 0.38),
      'DEF2' => const Alignment(-0.23, 0.38),
      'DEF3' => const Alignment(0.23, 0.38),
      'DEF4' => const Alignment(0.70, 0.38),
      'MID1' => const Alignment(-0.70, 0.0),
      'MID2' => const Alignment(-0.35, 0.0),
      'MID3' => const Alignment(0.0, 0.0),
      'MID4' => const Alignment(0.35, 0.0),
      'MID5' => const Alignment(0.70, 0.0),
      'FWD1' => const Alignment(-0.52, -0.38),
      'FWD2' => const Alignment(0.0, -0.38),
      'FWD3' => const Alignment(0.52, -0.38),
      _ => const Alignment(0.0, 0.0),
    };
  }

  String _lineKeyForSlot(Map<String, dynamic> slot) {
    final slotName = (slot['slot'] ?? '').toString().toUpperCase();
    if (slotName.startsWith('GK')) {
      return 'GK';
    }
    if (slotName.startsWith('DEF')) {
      return 'DEF';
    }
    if (slotName.startsWith('MID')) {
      return 'MID';
    }
    if (slotName.startsWith('FWD')) {
      return 'FWD';
    }

    return _posShort(slot['position']);
  }

  int _slotIndex(Map<String, dynamic> slot) {
    final slotName = (slot['slot'] ?? '').toString().toUpperCase();
    final m = RegExp(r'\d+$').firstMatch(slotName);
    if (m == null) {
      return 999;
    }
    return int.tryParse(m.group(0) ?? '') ?? 999;
  }

  List<double> _xPositionsForCount(int count) {
    return switch (count) {
      1 => const [0.0],
      2 => const [-0.30, 0.30],
      3 => const [-0.52, 0.0, 0.52],
      4 => const [-0.70, -0.23, 0.23, 0.70],
      5 => const [-0.78, -0.39, 0.0, 0.39, 0.78],
      _ => List.generate(
          count,
          (i) => count <= 1 ? 0.0 : -0.78 + (1.56 * i) / (count - 1),
        ),
    };
  }

  Map<String, Alignment> _dynamicPitchAlignments(
      List<Map<String, dynamic>> slots) {
    final byLine = <String, List<Map<String, dynamic>>>{
      'DEF': [],
      'MID': [],
      'FWD': [],
    };

    for (final slot in slots) {
      final line = _lineKeyForSlot(slot);
      if (line == 'DEF' || line == 'MID' || line == 'FWD') {
        byLine[line]!.add(slot);
      }
    }

    byLine['DEF']!.sort((a, b) => _slotIndex(a).compareTo(_slotIndex(b)));
    byLine['MID']!.sort((a, b) => _slotIndex(a).compareTo(_slotIndex(b)));
    byLine['FWD']!.sort((a, b) => _slotIndex(a).compareTo(_slotIndex(b)));

    final result = <String, Alignment>{};

    void assignLine(String line, double y) {
      final lineSlots = byLine[line]!;
      if (lineSlots.isEmpty) {
        return;
      }
      final xs = _xPositionsForCount(lineSlots.length);
      for (var i = 0; i < lineSlots.length; i++) {
        final key = (lineSlots[i]['slot'] ?? '').toString();
        result[key] = Alignment(xs[i], y);
      }
    }

    assignLine('DEF', 0.46);
    assignLine('MID', 0.0);
    assignLine('FWD', -0.50);

    return result;
  }

  Widget _playerCard(
    Map<String, dynamic> slot,
    BuildContext context, {
    required bool isCaptain,
    required bool isAssistant,
  }) {
    final posStr = _posShort(slot['position']);
    List<Color> fallbackPalette() => switch (posStr) {
          'GK' => [Colors.yellow.shade700, Colors.orange.shade800],
          'DEF' => [Colors.blue.shade500, Colors.blue.shade800],
          'MID' => [Colors.green.shade500, Colors.green.shade800],
          'FWD' => [Colors.red.shade500, Colors.red.shade900],
          _ => [
              Theme.of(context).colorScheme.primary,
              Theme.of(context).colorScheme.secondary,
            ],
        };

    String normalize(String value) => value.trim().toLowerCase();

    final shortName = slot['team_short_name']?.toString();
    final teamName = slot['team_name']?.toString();
    final kitColors = shortName != null &&
            _clubKitColors.containsKey(normalize(shortName))
        ? _clubKitColors[normalize(shortName)]!
        : teamName != null && _clubKitColors.containsKey(normalize(teamName))
            ? _clubKitColors[normalize(teamName)]!
            : fallbackPalette();
    final name = (slot['full_name'] ?? '').toString();
    final parts = name.trim().split(RegExp(r'\s+'));
    var displayName =
        parts.length > 1 ? '${parts.last} ${parts.first[0]}.' : name;
    if (isCaptain) {
      displayName = '$displayName (C)';
    } else if (isAssistant) {
      displayName = '$displayName (A)';
    }

    return Column(mainAxisSize: MainAxisSize.min, children: [
      SizedBox(
        width: 56,
        height: 60,
        child: Stack(
          alignment: Alignment.center,
          children: [
            const Positioned(
              left: 7,
              right: 7,
              bottom: 3,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  boxShadow: [
                    BoxShadow(
                      color: Color(0x33000000),
                      blurRadius: 4,
                      offset: Offset(0, 2),
                    ),
                  ],
                ),
                child: SizedBox(height: 1),
              ),
            ),
            CustomPaint(
              size: const Size(56, 60),
              painter: _JerseyPainter(
                primaryColor: kitColors[0],
                secondaryColor: kitColors[1],
              ),
            ),
          ],
        ),
      ),
      const SizedBox(height: 3),
      SizedBox(
          width: 92,
          child: Text(displayName,
              maxLines: 1,
              textAlign: TextAlign.center,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w700,
                  color: Colors.white))),
    ]);
  }

  Widget _lineupOnPitch(List<dynamic> rawSlots, BuildContext context) {
    final slots = rawSlots.cast<Map<String, dynamic>>();
    final dynamicAlignments = _dynamicPitchAlignments(slots);
    final roles = _captainAssistantIds(rawSlots);
    final captainId = roles['captain'];
    final assistantId = roles['assistant'];
    return LayoutBuilder(builder: (context, constraints) {
      final availW = constraints.maxWidth.isFinite
          ? constraints.maxWidth
          : MediaQuery.of(context).size.width;
      final pitchW = (availW / 2).clamp(240.0, 420.0);
      return Align(
        alignment: Alignment.center,
        child: SizedBox(
          width: pitchW,
          child: AspectRatio(
            aspectRatio: 340 / 520,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12),
              child: Stack(fit: StackFit.expand, children: [
                CustomPaint(painter: _PitchPainter()),
                ...slots.map((s) {
                  final playerId = (s['player_id'] is num)
                      ? (s['player_id'] as num).toInt()
                      : null;
                  return Align(
                      alignment:
                          dynamicAlignments[(s['slot'] ?? '').toString()] ??
                              _slotAlignment((s['slot'] ?? '').toString()),
                      child: _playerCard(
                        s,
                        context,
                        isCaptain: playerId != null && playerId == captainId,
                        isAssistant:
                            playerId != null && playerId == assistantId,
                      ));
                }),
              ]),
            ),
          ),
        ),
      );
    });
  }

  Widget _buildControlTab() {
    return ListView(padding: const EdgeInsets.all(12), children: [
      _sectionCard(title: 'Nastavení', children: [
        TextField(
          controller: _baseUrlController,
          decoration: const InputDecoration(
              labelText: 'Backend URL', hintText: 'http://127.0.0.1:8000'),
        ),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            onPressed: _busy ? null : _updateData,
            icon: const Icon(Icons.sync),
            label:
                Text(_isUpdating ? 'Aktualizuji...' : 'Update dat (FPL API)'),
          ),
          OutlinedButton.icon(
            onPressed: _busy ? null : _loadCurrentGw,
            icon: const Icon(Icons.refresh),
            label: Text(_isLoadingGw ? 'Načítám...' : 'Načíst aktuální kolo'),
          ),
          OutlinedButton.icon(
            onPressed: _busy ? null : () => _checkHealth(),
            icon: const Icon(Icons.monitor_heart_outlined),
            label:
                Text(_isCheckingHealth ? 'Kontroluji...' : 'Healthcheck API'),
          ),
        ]),
        const SizedBox(height: 10),
        Text(_status),
      ]),
      const SizedBox(height: 8),
      _buildHealthCard(),
      if (_currentGw != null) ...[
        const SizedBox(height: 8),
        _sectionCard(
            title: 'Aktuální kolo',
            children: [_buildCurrentGwInfo(_currentGw!)]),
        const SizedBox(height: 8),
        _buildFixturesCard(),
      ],
      if (_evaluation != null) ...[
        const SizedBox(height: 8),
        _buildEvaluationCard(_evaluation!),
      ],
    ]);
  }

  Widget _buildCurrentGwInfo(Map<String, dynamic> gw) {
    final isCurrent = gw['is_current'] == true;
    final isNext = gw['is_next'] == true;
    final finished = gw['finished'] == true;
    final deadline = gw['deadline_time']?.toString() ?? '-';
    String formattedDeadline = deadline;
    try {
      if (deadline != '-') {
        final dt = DateTime.parse(deadline).toLocal();
        formattedDeadline = '${dt.day}.${dt.month}.${dt.year} '
            '${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
      }
    } catch (_) {}
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        Text(gw['name']?.toString() ?? '-',
            style: Theme.of(context).textTheme.titleLarge),
        if (isCurrent) _chip('Aktuální', Colors.green),
        if (isNext) _chip('Příští', Colors.blue),
        if (finished) _chip('Dokončeno', Colors.grey),
      ]),
      const SizedBox(height: 4),
      Text('Deadline: $formattedDeadline'),
    ]);
  }

  Widget _buildEvaluationCard(Map<String, dynamic> ev) {
    return _sectionCard(
      title: 'Poslední evaluace (GW ${ev['gameweek_id']})',
      children: [
        Text('Backend: ${ev['backend']} | Hráčů: ${ev['evaluated_players']}'),
        const SizedBox(height: 4),
        Text(
            'MAE: ${_fmt(ev['mae'])} | RMSE: ${_fmt(ev['rmse'])} | Bias: ${_fmt(ev['bias'])}'),
        const SizedBox(height: 4),
        Text(
            'Lineup Δ: ${_fmt(ev['lineup_delta_actual_fpts'])} | Chybí historie: ${_fmt(ev['missing_history_rate'], digits: 1)}%'),
      ],
    );
  }

  Widget _buildClubLogo(String? logoUrl, {double size = 24}) {
    if (logoUrl == null || logoUrl.isEmpty) {
      return Container(
        width: size,
        height: size,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
        ),
        alignment: Alignment.center,
        child: Icon(Icons.shield_outlined,
            size: size * 0.65,
            color: Theme.of(context).colorScheme.onSurfaceVariant),
      );
    }
    return ClipOval(
      child: Image.network(
        logoUrl,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (_, __, ___) => Container(
          width: size,
          height: size,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Theme.of(context).colorScheme.surfaceContainerHighest,
          ),
          alignment: Alignment.center,
          child: Icon(Icons.shield_outlined,
              size: size * 0.65,
              color: Theme.of(context).colorScheme.onSurfaceVariant),
        ),
      ),
    );
  }

  Widget _buildFixturesCard() {
    if (_isLoadingFixtures && _fixtures.isEmpty) {
      return _sectionCard(
        title: 'Zápasy kola',
        children: const [
          Row(
            children: [
              SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              SizedBox(width: 10),
              Text('Načítám zápasy...'),
            ],
          ),
        ],
      );
    }

    return _sectionCard(
      title: 'Zápasy kola',
      children: [
        if (_fixtures.isEmpty)
          const Text('Pro toto kolo zatím nejsou dostupné zápasy.')
        else
          ..._fixtures.cast<Map<String, dynamic>>().map(_fixtureRow),
      ],
    );
  }

  Widget _fixtureRow(Map<String, dynamic> fx) {
    final homeName = fx['home_team_short_name']?.toString().isNotEmpty == true
        ? fx['home_team_short_name'].toString()
        : fx['home_team_name']?.toString() ?? '-';
    final awayName = fx['away_team_short_name']?.toString().isNotEmpty == true
        ? fx['away_team_short_name'].toString()
        : fx['away_team_name']?.toString() ?? '-';
    final homeLogo = _fixtureTeamLogoUrl(fx, 'home');
    final awayLogo = _fixtureTeamLogoUrl(fx, 'away');

    final started = fx['started'] == true;
    final finished = fx['finished'] == true;
    final scoreAvailable = fx['home_score'] != null && fx['away_score'] != null;
    final scoreText = scoreAvailable
        ? '${fx['home_score']} : ${fx['away_score']}'
        : started
            ? 'LIVE'
            : 'vs';

    String kickoffLabel = '-';
    final kickoffRaw = fx['kickoff_time']?.toString();
    if (kickoffRaw != null && kickoffRaw.isNotEmpty) {
      try {
        final dt = DateTime.parse(kickoffRaw).toLocal();
        kickoffLabel =
            '${dt.day}.${dt.month}. ${dt.hour.toString().padLeft(2, '0')}:${dt.minute.toString().padLeft(2, '0')}';
      } catch (_) {
        kickoffLabel = kickoffRaw;
      }
    }

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        children: [
          Expanded(
            child: Row(
              children: [
                _buildClubLogo(homeLogo, size: 24),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(homeName,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ),
              ],
            ),
          ),
          SizedBox(
            width: 72,
            child: Column(
              children: [
                Text(scoreText,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                        fontWeight: FontWeight.w800,
                        color: finished
                            ? Theme.of(context).colorScheme.primary
                            : Theme.of(context).colorScheme.onSurface)),
                Text(kickoffLabel,
                    style: TextStyle(
                        fontSize: 11,
                        color: Theme.of(context).colorScheme.onSurfaceVariant)),
              ],
            ),
          ),
          Expanded(
            child: Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                Expanded(
                  child: Text(awayName,
                      textAlign: TextAlign.end,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(fontWeight: FontWeight.w600)),
                ),
                const SizedBox(width: 8),
                _buildClubLogo(awayLogo, size: 24),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHealthCard() {
    final health = _health;
    final checkedAt = _healthCheckedAt;
    final checkedAtLabel = checkedAt == null
        ? '-'
        : '${checkedAt.hour.toString().padLeft(2, '0')}:${checkedAt.minute.toString().padLeft(2, '0')}:${checkedAt.second.toString().padLeft(2, '0')}';

    if (_isCheckingHealth && health == null && _healthError == null) {
      return _sectionCard(
        title: 'Healthcheck API',
        children: const [
          Row(
            children: [
              SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
              SizedBox(width: 10),
              Text('Kontroluji dostupnost backendu...'),
            ],
          ),
        ],
      );
    }

    if (_healthError != null) {
      return _sectionCard(
        title: 'Healthcheck API',
        children: [
          Row(
            children: [
              const Icon(Icons.error_outline, color: Colors.red),
              const SizedBox(width: 8),
              Text(
                'API nedostupné',
                style: TextStyle(
                  color: Colors.red.shade700,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text('Důvod: $_healthError'),
          const SizedBox(height: 4),
          Text('Poslední kontrola: $checkedAtLabel'),
        ],
      );
    }

    return _sectionCard(
      title: 'Healthcheck API',
      children: [
        Row(
          children: [
            Icon(
              (health?['status']?.toString().toLowerCase() == 'ok')
                  ? Icons.check_circle_outline
                  : Icons.info_outline,
              color: (health?['status']?.toString().toLowerCase() == 'ok')
                  ? Colors.green
                  : Theme.of(context).colorScheme.primary,
            ),
            const SizedBox(width: 8),
            Text(
              'Status: ${health?['status'] ?? 'neznámý'}',
              style: const TextStyle(fontWeight: FontWeight.w700),
            ),
          ],
        ),
        const SizedBox(height: 6),
        Text('Databáze: ${health?['database'] ?? '-'}'),
        const SizedBox(height: 4),
        Text('Poslední kontrola: $checkedAtLabel'),
      ],
    );
  }

  Widget _buildLineupTab() {
    final lineupSlots = (_lineup?['slots'] as List<dynamic>? ?? [])
        .cast<Map<String, dynamic>>();
    final roles = _captainAssistantIds(lineupSlots);
    final captainId = roles['captain'];
    final assistantId = roles['assistant'];

    return ListView(padding: const EdgeInsets.all(12), children: [
      _sectionCard(title: 'Sestava', children: [
        if (_currentGw == null)
          const Text('Nejdříve načti aktuální kolo (záložka Přehled).')
        else ...[
          Text('Kolo: ${_currentGw!['name']}'),
          const SizedBox(height: 10),
          Wrap(spacing: 8, runSpacing: 8, children: [
            FilledButton.icon(
              onPressed: _busy ? null : _loadLineup,
              icon: const Icon(Icons.auto_awesome),
              label:
                  Text(_isLoadingLineup ? 'Generuji...' : 'Doporučit sestavu'),
            ),
            OutlinedButton.icon(
              onPressed: _busy ? null : _evaluate,
              icon: const Icon(Icons.analytics_outlined),
              label: Text(_isEvaluating ? 'Vyhodnocuji...' : 'Evaluate kolo'),
            ),
            if (_lockedPlayerIds.isNotEmpty || _excludedPlayerIds.isNotEmpty)
              TextButton(
                onPressed: _busy
                    ? null
                    : () => setState(() {
                          _lockedPlayerIds.clear();
                          _excludedPlayerIds.clear();
                        }),
                child: const Text('Vyčistit lock / exclude'),
              ),
          ]),
          if (_lockedPlayerIds.isNotEmpty || _excludedPlayerIds.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
                'Uzamčeno: ${_lockedPlayerIds.length} | Vyloučeno: ${_excludedPlayerIds.length}',
                style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant)),
          ],
        ],
      ]),
      if (_lineup != null) ...[
        const SizedBox(height: 8),
        _sectionCard(
          title:
              'Doporučená sestava | ${_fmt(_lineup!['total_fpts'], digits: 1)} b. | ${_lineup!['total_salary_display'] ?? ''}',
          children: [
            SegmentedButton<bool>(
              segments: const [
                ButtonSegment(
                    value: true,
                    icon: Icon(Icons.sports_soccer),
                    label: Text('Hřiště')),
                ButtonSegment(
                    value: false,
                    icon: Icon(Icons.view_list),
                    label: Text('Seznam')),
              ],
              selected: {_showPitchView},
              onSelectionChanged: (v) =>
                  setState(() => _showPitchView = v.first),
            ),
            const SizedBox(height: 12),
            if (_showPitchView)
              _lineupOnPitch(_lineup!['slots'] as List<dynamic>, context)
            else
              ...lineupSlots.map((s) {
                final playerId = (s['player_id'] is num)
                    ? (s['player_id'] as num).toInt()
                    : null;
                final isCaptain = playerId != null && playerId == captainId;
                final isAssistant = playerId != null && playerId == assistantId;
                final roleSuffix = isCaptain
                    ? ' (C)'
                    : isAssistant
                        ? ' (A)'
                        : '';
                final logoUrl = _teamLogoUrlFromMap(s);
                return ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: SizedBox(
                    width: 62,
                    child: Row(
                      children: [
                        _buildClubLogo(logoUrl, size: 28),
                        const SizedBox(width: 6),
                        CircleAvatar(
                          radius: 12,
                          backgroundColor:
                              Theme.of(context).colorScheme.primaryContainer,
                          child: Text(_posShort(s['position']),
                              style: TextStyle(
                                  fontSize: 9,
                                  fontWeight: FontWeight.w700,
                                  color: Theme.of(context)
                                      .colorScheme
                                      .onPrimaryContainer)),
                        ),
                      ],
                    ),
                  ),
                  title:
                      Text('${s['full_name']?.toString() ?? '-'}$roleSuffix'),
                  subtitle: Text(
                      '${_posName(s['position'])} | ${s['salary_display']} '
                      '| ${_fmt(s['projected_fpts'], digits: 1)} b. | Slot: ${s['slot']}'),
                );
              }),
          ],
        ),
      ],
    ]);
  }

  Widget _buildProjectionsTab() {
    return ListView(padding: const EdgeInsets.all(12), children: [
      _sectionCard(title: 'Projekce hráčů', children: [
        if (_currentGw == null)
          const Text('Nejdříve načti aktuální kolo (záložka Přehled).')
        else
          Wrap(spacing: 8, runSpacing: 8, children: [
            FilledButton.icon(
              onPressed: _busy ? null : () => _loadProjections(rebuild: false),
              icon: const Icon(Icons.list),
              label: Text(
                  _isLoadingProjections ? 'Načítám...' : 'Načíst projekce'),
            ),
            OutlinedButton.icon(
              onPressed: _busy ? null : () => _loadProjections(rebuild: true),
              icon: const Icon(Icons.refresh),
              label: const Text('Regenerovat projekce'),
            ),
          ]),
      ]),
      if (_projections.isNotEmpty) ...[
        const SizedBox(height: 8),
        _sectionCard(
          title: 'Top hráči (${_projections.length})',
          children: _projections
              .take(30)
              .cast<Map<String, dynamic>>()
              .map(_projectionRow)
              .toList(),
        ),
      ],
    ]);
  }

  Widget _projectionRow(Map<String, dynamic> p) {
    final playerId =
        (p['player_id'] is num) ? (p['player_id'] as num).toInt() : null;
    final isLocked = playerId != null && _lockedPlayerIds.contains(playerId);
    final isExcluded =
        playerId != null && _excludedPlayerIds.contains(playerId);
    final injury = p['injury_flag'] == true;
    final winProb = p['team_win_prob'];
    final avg5 = p['rolling_avg_fpts_5g'];
    final avg10 = p['rolling_avg_fpts_10g'];
    final parts = <String>[
      _posName(p['position']),
      p['salary_display']?.toString() ?? '',
      'Proj: ${_fmt(p['projected_fpts'], digits: 1)} b.',
      if (avg5 != null) 'Forma 5z.: ${_fmt(avg5, digits: 1)}',
      if (avg10 != null) 'Avg 10z.: ${_fmt(avg10, digits: 1)}',
      if (winProb != null)
        'Výhra: ${((winProb as num) * 100).toStringAsFixed(0)} %',
      if (injury) '⚠ Zraněný',
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          Expanded(
              child: Text(p['full_name']?.toString() ?? '-',
                  style: const TextStyle(fontWeight: FontWeight.bold))),
          Text('${_fmt(p['projected_fpts'], digits: 1)} b.',
              style: TextStyle(
                  fontWeight: FontWeight.w700,
                  color: Theme.of(context).colorScheme.primary)),
        ]),
        const SizedBox(height: 2),
        Text(parts.join('  ·  '),
            style: TextStyle(
                fontSize: 12,
                color: Theme.of(context).colorScheme.onSurfaceVariant)),
        const SizedBox(height: 6),
        Wrap(spacing: 8, runSpacing: 6, children: [
          FilterChip(
            label: const Text('Uzamknout'),
            selected: isLocked,
            onSelected: _busy || playerId == null
                ? null
                : (v) => setState(() {
                      if (v) {
                        _lockedPlayerIds.add(playerId);
                        _excludedPlayerIds.remove(playerId);
                      } else {
                        _lockedPlayerIds.remove(playerId);
                      }
                    }),
          ),
          FilterChip(
            label: const Text('Vyloučit'),
            selected: isExcluded,
            onSelected: _busy || playerId == null
                ? null
                : (v) => setState(() {
                      if (v) {
                        _excludedPlayerIds.add(playerId);
                        _lockedPlayerIds.remove(playerId);
                      } else {
                        _excludedPlayerIds.remove(playerId);
                      }
                    }),
          ),
        ]),
        const Divider(height: 12),
      ]),
    );
  }

  Widget _buildReportTab() {
    final report = _evaluationReport;
    return ListView(padding: const EdgeInsets.all(12), children: [
      _sectionCard(title: 'Filtrování reportu', children: [
        Row(children: [
          Expanded(
            child: DropdownButtonFormField<int>(
              decoration: const InputDecoration(labelText: 'Počet kol'),
              initialValue: _reportRows,
              items: const [
                DropdownMenuItem(value: 5, child: Text('5')),
                DropdownMenuItem(value: 10, child: Text('10')),
                DropdownMenuItem(value: 20, child: Text('20')),
                DropdownMenuItem(value: 34, child: Text('34')),
              ],
              onChanged: (v) => setState(() => _reportRows = v ?? 10),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: DropdownButtonFormField<String>(
              decoration: const InputDecoration(labelText: 'Primární metrika'),
              initialValue: _primaryWinnerMetric,
              items: const [
                DropdownMenuItem(value: 'mae', child: Text('MAE')),
                DropdownMenuItem(
                    value: 'lineup_delta_abs', child: Text('Lineup Δ abs')),
              ],
              onChanged: (v) =>
                  setState(() => _primaryWinnerMetric = v ?? 'mae'),
            ),
          ),
        ]),
        const SizedBox(height: 10),
        Row(children: [
          Expanded(
            child: TextFormField(
              controller: _fromGwController,
              decoration: const InputDecoration(
                  labelText: 'Od kola (1–38)', hintText: 'nepovinné'),
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              onChanged: (v) => _reportFromGw =
                  v.trim().isEmpty ? null : int.tryParse(v.trim()),
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: TextFormField(
              controller: _toGwController,
              decoration: const InputDecoration(
                  labelText: 'Do kola (1–38)', hintText: 'nepovinné'),
              keyboardType: TextInputType.number,
              inputFormatters: [FilteringTextInputFormatter.digitsOnly],
              onChanged: (v) => _reportToGw =
                  v.trim().isEmpty ? null : int.tryParse(v.trim()),
            ),
          ),
        ]),
        const SizedBox(height: 12),
        FilledButton.icon(
          onPressed: _busy ? null : _loadReport,
          icon: const Icon(Icons.bar_chart),
          label: Text(_isLoadingReport ? 'Načítám...' : 'Načíst report'),
        ),
      ]),
      if (report != null) ...[
        const SizedBox(height: 8),
        _buildReportContent(report),
      ],
    ]);
  }

  Widget _buildReportContent(Map<String, dynamic> report) {
    final rows =
        (report['rows'] as List<dynamic>? ?? []).cast<Map<String, dynamic>>();
    final trendMae =
        report['backend_winner_trend_mae'] as Map<String, dynamic>?;
    final trendDelta =
        report['backend_winner_trend_lineup_delta'] as Map<String, dynamic>?;
    final timeline = (report['winner_timeline'] as List<dynamic>? ?? [])
        .cast<Map<String, dynamic>>();
    final primaryMetric = report['primary_winner_metric']?.toString() ?? 'mae';
    final appliedFrom = report['applied_from_gameweek'];
    final appliedTo = report['applied_to_gameweek'];

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      if (trendMae != null || trendDelta != null)
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          if (trendMae != null)
            Expanded(child: _trendCard('Trend (MAE)', trendMae)),
          if (trendMae != null && trendDelta != null) const SizedBox(width: 8),
          if (trendDelta != null)
            Expanded(child: _trendCard('Trend (Lineup Δ)', trendDelta)),
        ]),
      const SizedBox(height: 8),
      _sectionCard(
        title: [
          'Detail kol',
          if (appliedFrom != null) ' od GW$appliedFrom',
          if (appliedTo != null) ' do GW$appliedTo',
          ' · primární: ',
          primaryMetric == 'mae' ? 'MAE' : 'Lineup Δ abs',
        ].join(),
        children: [
          if (rows.isEmpty)
            const Text('Zatím nejsou žádná data evaluací.')
          else
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DataTable(
                columnSpacing: 14,
                headingRowHeight: 36,
                dataRowMinHeight: 32,
                dataRowMaxHeight: 40,
                columns: const [
                  DataColumn(
                      label: Text('Kolo', style: TextStyle(fontSize: 12))),
                  DataColumn(
                      label: Text('Hráčů', style: TextStyle(fontSize: 12)),
                      numeric: true),
                  DataColumn(
                      label: Text('MAE', style: TextStyle(fontSize: 12)),
                      numeric: true),
                  DataColumn(
                      label: Text('RMSE', style: TextStyle(fontSize: 12)),
                      numeric: true),
                  DataColumn(
                      label: Text('Bias', style: TextStyle(fontSize: 12)),
                      numeric: true),
                  DataColumn(
                      label: Text('Δ Lineup', style: TextStyle(fontSize: 12)),
                      numeric: true),
                  DataColumn(
                      label: Text('W (prim.)', style: TextStyle(fontSize: 12))),
                  DataColumn(
                      label: Text('W (MAE)', style: TextStyle(fontSize: 12))),
                  DataColumn(
                      label: Text('W (Δ)', style: TextStyle(fontSize: 12))),
                ],
                rows: rows
                    .map((r) => DataRow(cells: [
                          DataCell(Text(r['gw_name']?.toString() ?? '-',
                              style: const TextStyle(fontSize: 12))),
                          DataCell(Text(
                              r['evaluated_players']?.toString() ?? '-',
                              style: const TextStyle(fontSize: 12))),
                          DataCell(Text(_fmt(r['mae']),
                              style: const TextStyle(fontSize: 12))),
                          DataCell(Text(_fmt(r['rmse']),
                              style: const TextStyle(fontSize: 12))),
                          DataCell(Text(_fmt(r['bias']),
                              style: const TextStyle(fontSize: 12))),
                          DataCell(Text(_fmt(r['lineup_delta_actual_fpts']),
                              style: const TextStyle(fontSize: 12))),
                          DataCell(_winnerBadge(
                              r['backend_winner']?.toString(), context)),
                          DataCell(_winnerBadge(
                              r['backend_winner_mae']?.toString(), context)),
                          DataCell(_winnerBadge(
                              r['backend_winner_lineup_delta']?.toString(),
                              context)),
                        ]))
                    .toList(),
              ),
            ),
        ],
      ),
      if (timeline.isNotEmpty) ...[
        const SizedBox(height: 8),
        _sectionCard(
            title: 'MAE Timeline',
            children: timeline.map(_timelineRow).toList()),
      ],
    ]);
  }

  Widget _trendCard(String title, Map<String, dynamic> trend) {
    final baseWins = trend['baseline_wins'] as int? ?? 0;
    final mlWins = trend['ml_wins'] as int? ?? 0;
    final ties = trend['ties'] as int? ?? 0;
    final total = trend['compared_gameweeks'] as int? ?? 0;
    final baseRate = trend['baseline_win_rate'];
    final mlRate = trend['ml_win_rate'];
    final winner = baseWins > mlWins
        ? 'Baseline vede'
        : mlWins > baseWins
            ? 'ML vede'
            : 'Remíza';
    final winColor = baseWins > mlWins
        ? Colors.orange.shade700
        : mlWins > baseWins
            ? Colors.blue.shade700
            : Theme.of(context).colorScheme.onSurface;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: 6),
          Text(winner,
              style: TextStyle(
                  fontWeight: FontWeight.w800, fontSize: 16, color: winColor)),
          const SizedBox(height: 4),
          Text(
              'Baseline: $baseWins/$total (${_fmt(baseRate != null ? (baseRate as num) * 100 : null, digits: 0)} %)',
              style: const TextStyle(fontSize: 12)),
          Text(
              'ML: $mlWins/$total (${_fmt(mlRate != null ? (mlRate as num) * 100 : null, digits: 0)} %)',
              style: const TextStyle(fontSize: 12)),
          Text('Remízy: $ties', style: const TextStyle(fontSize: 12)),
        ]),
      ),
    );
  }

  Widget _timelineRow(Map<String, dynamic> t) {
    final baselineMae = (t['baseline_mae'] as num?)?.toDouble();
    final mlMae = (t['ml_mae'] as num?)?.toDouble();
    final maxMae =
        [baselineMae ?? 0.0, mlMae ?? 0.0].reduce((a, b) => a > b ? a : b);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(t['gw_name']?.toString() ?? '-',
            style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 12)),
        const SizedBox(height: 3),
        Row(children: [
          const SizedBox(
              width: 60,
              child: Text('Baseline', style: TextStyle(fontSize: 10))),
          Expanded(
              child: LinearProgressIndicator(
            value: maxMae > 0 ? (baselineMae ?? 0) / maxMae : 0,
            backgroundColor: Colors.orange.withAlpha(26),
            valueColor: AlwaysStoppedAnimation<Color>(Colors.orange.shade400),
            minHeight: 8,
            borderRadius: BorderRadius.circular(4),
          )),
          const SizedBox(width: 6),
          SizedBox(
              width: 36,
              child: Text(_fmt(baselineMae),
                  style: const TextStyle(fontSize: 10),
                  textAlign: TextAlign.end)),
        ]),
        const SizedBox(height: 2),
        Row(children: [
          const SizedBox(
              width: 60, child: Text('ML', style: TextStyle(fontSize: 10))),
          Expanded(
              child: LinearProgressIndicator(
            value: maxMae > 0 ? (mlMae ?? 0) / maxMae : 0,
            backgroundColor: Colors.blue.withAlpha(26),
            valueColor: AlwaysStoppedAnimation<Color>(Colors.blue.shade400),
            minHeight: 8,
            borderRadius: BorderRadius.circular(4),
          )),
          const SizedBox(width: 6),
          SizedBox(
              width: 36,
              child: Text(_fmt(mlMae),
                  style: const TextStyle(fontSize: 10),
                  textAlign: TextAlign.end)),
        ]),
      ]),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 4,
      child: Scaffold(
        appBar: AppBar(
          title: const Text('Fantasy PM Helper'),
          actions: [
            if (_busy)
              const Padding(
                padding: EdgeInsets.only(right: 16),
                child: SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2)),
              ),
          ],
          bottom: const TabBar(tabs: [
            Tab(icon: Icon(Icons.home), text: 'Přehled'),
            Tab(icon: Icon(Icons.sports_soccer), text: 'Sestava'),
            Tab(icon: Icon(Icons.people), text: 'Projekce'),
            Tab(icon: Icon(Icons.bar_chart), text: 'Evaluace'),
          ]),
        ),
        body: TabBarView(children: [
          _buildControlTab(),
          _buildLineupTab(),
          _buildProjectionsTab(),
          _buildReportTab(),
        ]),
      ),
    );
  }
}

import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router'
import type { Profile } from '../api/client'
import { errorMessage } from '../api/errors'
import { queryKeys, useLibraryHome, useProfiles, useSetupStatus, useStartSession } from '../api/queries'
import { phrase } from '../audio/phrases'
import { speak } from '../audio/speech'
import Badge from '../components/Badge/Badge'
import HomeCard from '../components/HomeCard/HomeCard'
import SpeakerButton from '../components/SpeakerButton/SpeakerButton'
import { getCurrentProfileId, setCurrentProfileId } from '../profile'
import ProfilePicker from './ProfilePicker'
import ParentLock from './ParentLock'

/**
 * The child-facing Home (Story 2.3): a Profile picker (skipped when there is only one
 * Profile), then "Học tiếp" (the first Lesson with a visible Problem, in the child's own
 * Grade) and "Sách" (Library). Keeps `Home`'s original setup-redirect/loading/error
 * handling around the (former placeholder) server-status screen.
 */
export default function Home() {
  const setup = useSetupStatus()
  const profiles = useProfiles()
  const [profileId, setProfileId] = useState<string | null>(() => getCurrentProfileId())

  const list = profiles.data ?? []
  const onlyProfile = list.length === 1 ? list[0] : undefined

  // Exactly one Profile: it becomes "current" for this browser session without a picker.
  // `current` below already falls back to `onlyProfile` the moment it is known, so this
  // effect only needs to persist it -- never a `setState` that would trigger another render.
  useEffect(() => {
    if (onlyProfile) setCurrentProfileId(onlyProfile.id)
  }, [onlyProfile])

  if (setup.data?.setup_required) return <Navigate to="/setup" replace />

  if (setup.isPending || profiles.isPending) {
    return (
      <main className="home">
        <p>Đang tải…</p>
      </main>
    )
  }

  if (setup.isError) {
    return (
      <main className="home">
        <h1>Học Tập</h1>
        <p role="alert" className="form-error">
          {errorMessage(setup.error)}
        </p>
        <button type="button" onClick={() => void setup.refetch()}>
          Thử lại
        </button>
      </main>
    )
  }

  if (profiles.isError) {
    return (
      <main className="home">
        <h1>Học Tập</h1>
        <p role="alert" className="form-error">
          {errorMessage(profiles.error)}
        </p>
        <button type="button" onClick={() => void profiles.refetch()}>
          Thử lại
        </button>
      </main>
    )
  }

  // `setup_required: false` with zero Profiles is an inconsistent but reachable state
  // (e.g. the sole Profile deleted from the Parent Area post-setup) -- without this guard
  // it would leave a dead-end blank ProfilePicker with nothing to pick.
  if (list.length === 0) return <Navigate to="/setup" replace />

  const current = list.find((p) => p.id === profileId) ?? onlyProfile

  if (!current) {
    return (
      <ProfilePicker
        profiles={list}
        onSelect={(id) => {
          setCurrentProfileId(id)
          setProfileId(id)
        }}
      />
    )
  }

  return <HomeContent profile={current} />
}

function HomeContent({ profile }: { profile: Profile }) {
  const navigate = useNavigate()
  const home = useLibraryHome(profile.id)
  const startSession = useStartSession()
  const queryClient = useQueryClient()
  // Which card started the failing/last Session, so its error shows next to that card.
  const [startedFrom, setStartedFrom] = useState<'assignment' | 'lesson' | 'retry'>('lesson')
  const lesson = home.data?.lesson
  const continueSession = home.data?.continue_session
  const keepLearningLabel = phrase('home_keep_learning')
  const libraryLabel = phrase('home_library')
  const continueLabel = phrase('home_continue')
  const badgesLabel = phrase('your_badges')
  const retryDue = (home.data?.retry_due_count ?? 0) > 0
  const practiceAgainLabel = phrase('home_practice_again')
  const recentBadges = home.data?.recent_badges ?? []

  const startLesson = () => {
    if (!lesson) return
    setStartedFrom('lesson')
    startSession.mutate(
      {
        profileId: profile.id,
        ref: {
          kind: 'lesson',
          book_id: lesson.book_id,
          unit_key: lesson.unit_key,
          lesson_key: lesson.lesson_key,
        },
      },
      { onSuccess: (session) => navigate(`/sessions/${session.id}`) },
    )
  }

  const assignment = home.data?.assignment
  const todayLabel = phrase('home_today_lesson')
  const yesterdayLabel = phrase('home_yesterday')

  const openAssignment = () => {
    if (!assignment) return
    if (assignment.session_id) {
      navigate(`/sessions/${assignment.session_id}`)
      return
    }
    if (startSession.isPending) return // a second tap must not start a second Session
    setStartedFrom('assignment')
    startSession.mutate(
      {
        profileId: profile.id,
        assignmentId: assignment.id,
        ref: {
          kind: 'lesson',
          book_id: assignment.book_id,
          unit_key: assignment.unit_key,
          lesson_key: assignment.lesson_key,
        },
      },
      {
        onSuccess: (session) => navigate(`/sessions/${session.id}`),
        // E.g. ASSIGNMENT_DONE / 404: refetch Home so a stale card goes away.
        onError: () =>
          void queryClient.invalidateQueries({ queryKey: queryKeys.libraryHome(profile.id) }),
      },
    )
  }

  const startRetry = () => {
    setStartedFrom('retry')
    startSession.mutate(
      { profileId: profile.id, ref: { kind: 'retry' }, mode: 'retry' },
      { onSuccess: (session) => navigate(`/sessions/${session.id}`) },
    )
  }

  return (
    <main className="home">
      <h1>Học Tập</h1>
      {home.data && (home.data.total_stars > 0 || home.data.streak > 0) && (
        <p className="home-stars-streak" data-testid="home-stars-streak">
          <span>
            ⭐ {home.data.total_stars} {phrase('total_stars')}
          </span>
          {home.data.streak > 0 && (
            <span>
              {' '}
              · 🔥 {home.data.streak} {phrase('current_streak')}
            </span>
          )}
        </p>
      )}
      {recentBadges.length > 0 && (
        <div className="home-recent-badges" data-testid="home-recent-badges">
          {recentBadges.map((badgeKey) => (
            <Badge key={badgeKey} badgeKey={badgeKey} earned small />
          ))}
        </div>
      )}
      <div className="home-cards">
        {assignment && (
          <div className="home-card-slot" data-testid="home-assignment">
            {assignment.carried_over && (
              <span className="home-ribbon" data-testid="home-assignment-ribbon">
                {yesterdayLabel}
              </span>
            )}
            <HomeCard
              title={todayLabel}
              icon="⭐"
              wide
              onClick={openAssignment}
              onLongPress={() => void speak(todayLabel)}
            >
              <span className="home-card-subtitle">
                {assignment.lesson_label}
                {assignment.part != null &&
                  assignment.part_count != null &&
                  ` · Phần ${assignment.part}/${assignment.part_count}`}
              </span>
            </HomeCard>
            <SpeakerButton label={`Nghe: ${todayLabel}`} onClick={() => void speak(todayLabel)} />
            {startSession.isError && startedFrom === 'assignment' && (
              <p role="alert" className="form-error">
                {errorMessage(startSession.error)}
              </p>
            )}
          </div>
        )}
        <div className="home-card-slot">
          {home.isPending ? (
            <p>Đang tải…</p>
          ) : home.isError ? (
            <div>
              <p role="alert" className="form-error">
                {errorMessage(home.error)}
              </p>
              <button type="button" onClick={() => void home.refetch()}>
                Thử lại
              </button>
            </div>
          ) : lesson ? (
            <>
              <HomeCard
                title={keepLearningLabel}
                icon="📖"
                wide
                onClick={startLesson}
                onLongPress={() => void speak(keepLearningLabel)}
              />
              <SpeakerButton
                label={`Nghe: ${keepLearningLabel}`}
                onClick={() => void speak(keepLearningLabel)}
              />
              {startSession.isError && startedFrom === 'lesson' && (
                <p role="alert" className="form-error">
                  {errorMessage(startSession.error)}
                </p>
              )}
            </>
          ) : (
            <p className="home-empty" data-testid="home-empty">
              {phrase('home_nothing_yet')}
            </p>
          )}
        </div>
        <div className="home-card-slot">
          <HomeCard
            title={libraryLabel}
            icon="📚"
            onClick={() => navigate('/library')}
            onLongPress={() => void speak(libraryLabel)}
          />
          <SpeakerButton label={`Nghe: ${libraryLabel}`} onClick={() => void speak(libraryLabel)} />
        </div>
        <div className="home-card-slot">
          <HomeCard
            title={badgesLabel}
            icon="🏅"
            onClick={() => navigate('/badges')}
            onLongPress={() => void speak(badgesLabel)}
          />
          <SpeakerButton label={`Nghe: ${badgesLabel}`} onClick={() => void speak(badgesLabel)} />
        </div>
        {retryDue && (
          <div className="home-card-slot">
            <HomeCard
              title={practiceAgainLabel}
              icon="🔁"
              onClick={startRetry}
              onLongPress={() => void speak(practiceAgainLabel)}
            />
            <SpeakerButton
              label={`Nghe: ${practiceAgainLabel}`}
              onClick={() => void speak(practiceAgainLabel)}
            />
            {startSession.isError && startedFrom === 'retry' && (
              <p role="alert" className="form-error">
                {errorMessage(startSession.error)}
              </p>
            )}
          </div>
        )}
        {continueSession && (
          <div className="home-card-slot">
            <HomeCard
              title={continueLabel}
              icon="↩️"
              onClick={() => navigate(`/sessions/${continueSession.session_id}`)}
              onLongPress={() => void speak(continueLabel)}
            />
            <SpeakerButton label={`Nghe: ${continueLabel}`} onClick={() => void speak(continueLabel)} />
          </div>
        )}
      </div>
      <p className="parent-link">
        <ParentLock onOpen={() => navigate('/parent/login')} />
      </p>
    </main>
  )
}

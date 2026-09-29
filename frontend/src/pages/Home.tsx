import { useEffect, useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router'
import type { Profile } from '../api/client'
import { errorMessage } from '../api/errors'
import { useLibraryHome, useProfiles, useSetupStatus, useStartSession } from '../api/queries'
import { phrase } from '../audio/phrases'
import { speak } from '../audio/speech'
import Badge from '../components/Badge/Badge'
import HomeCard from '../components/HomeCard/HomeCard'
import SpeakerButton from '../components/SpeakerButton/SpeakerButton'
import { getCurrentProfileId, setCurrentProfileId } from '../profile'
import ProfilePicker from './ProfilePicker'

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

  const startRetry = () => {
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
              {startSession.isError && (
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
            {startSession.isError && !lesson && (
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
        <Link to="/parent/login">Khu vực phụ huynh</Link>
      </p>
    </main>
  )
}
